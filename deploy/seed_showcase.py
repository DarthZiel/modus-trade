"""Load a presentation fixture into existing accounts; never reset user data.

Run inside the backend container. JSON arrives on stdin. Default: validate only.
The provenance and stable namespace live in the operator manifest, not UI copy.
"""

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlmodel import Session, select

from app.appeal_schemas import AppealInput, AppealStatus
from app.database import engine
from app.models import (
    Appeal, AppealEvent, AppealFeedback, AppealMessage, Experiment,
    Notification, User, utcnow,
)
from pydantic import TypeAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = json.load(sys.stdin)
    namespace = data['namespace']
    items = data['appeals']
    assert items and len({item['key'] for item in items}) == len(items)
    ids = {item['key']: uuid5(NAMESPACE_URL, namespace + ':' + item['key']) for item in items}
    for item in items:
        AppealInput.model_validate({
            'kind': item['kind'], 'title': item['title'],
            'description': item['description'], 'category': item['category'],
            'submission_id': ids[item['key']],
        })
        TypeAdapter(AppealStatus).validate_python(item['status'])
        assert item['age_hours'] > 0
        if item['status'] in {'awaiting_confirmation', 'closed', 'rejected'}:
            assert item.get('result') and item.get('decided_age_hours') is not None
        if item['status'] == 'closed':
            assert item.get('feedback', {}).get('outcome') == 'helped'
        if item['status'] == 'needs_info':
            assert item.get('resume_status') in {'reviewing', 'in_progress'}
    with Session(engine) as db, db.begin():
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': namespace})
        users = {
            role: db.exec(select(User).where(User.email == email)).one()
            for role, email in data['accounts'].items()
        }
        assert all(user.is_active for user in users.values())
        assert 'coordinator' in users['coordinator'].roles
        assert 'responsible' in users['responsible'].roles
        assert len({user.company_id for user in users.values()}) == 1
        existing = db.exec(select(Appeal).where(Appeal.submission_id.in_(ids.values()))).all()
        if existing:
            assert len(existing) == len(items), 'Partial fixture found; manual review required.'
            print('Fixture already exists; no records changed.')
            return
        if not args.apply:
            print(f'Validated {len(items)} appeals against existing accounts; no data written.')
            return
        now = utcnow()
        stamp = lambda hours: now - timedelta(hours=hours)
        coordinators = db.exec(select(User).where(User.is_active)).all()
        coordinators = [user for user in coordinators if 'coordinator' in user.roles]
        for item in items:
            author = users[item.get('author', 'employee')]
            responsible = users['responsible'] if item['status'] != 'received' else None
            appeal = Appeal(
                submission_id=ids[item['key']],
                payload_hash=hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(),
                kind=item['kind'], title=item['title'], description=item['description'],
                original_description=item['description'], category=item['category'],
                author_id=author.id, company_id=author.company_id, department_id=author.department_id,
                status=item['status'], responsible_id=responsible.id if responsible else None,
                resume_status=item.get('resume_status'),
                next_response_at=stamp(item['due_age_hours']) if item.get('due_age_hours') is not None else None,
                decision=item.get('decision'), result=item.get('result'),
                decided_at=stamp(item['decided_age_hours']) if item.get('decided_age_hours') is not None else None,
                assignment_version=len(item.get('events', [])), created_at=stamp(item['age_hours']),
            )
            db.add(appeal)
            db.flush()
            for event in item['events']:
                assert 0 <= event['age_hours'] <= item['age_hours']
                db.add(AppealEvent(appeal_id=appeal.id, actor_id=users[event['actor']].id,
                                   text=event['text'], created_at=stamp(event['age_hours'])))
            for index, message in enumerate(item.get('messages', [])):
                assert 0 <= message['age_hours'] <= item['age_hours']
                db.add(AppealMessage(
                    appeal_id=appeal.id, sender_id=users[message['actor']].id,
                    client_id=uuid5(ids[item['key']], f'message:{index}'), body=message['body'],
                    kind=message.get('kind', 'message'), created_at=stamp(message['age_hours']),
                ))
            if item.get('feedback'):
                feedback = item['feedback']
                db.add(AppealFeedback(
                    appeal_id=appeal.id, author_id=author.id,
                    client_id=uuid5(ids[item['key']], 'feedback'), outcome=feedback['outcome'],
                    comment=feedback['comment'], result_snapshot=feedback['result_snapshot'],
                    created_at=stamp(feedback['age_hours']),
                ))
            if item.get('experiment'):
                exp = dict(item['experiment'])
                starts = exp.pop('starts_age_hours')
                ends = exp.pop('ends_age_hours')
                finished = exp.pop('finished_age_hours', None)
                created = exp.pop('created_age_hours', starts)
                assert starts > ends
                assert item['age_hours'] >= created >= starts
                assert exp['status'] != 'active' or item['status'] == 'in_progress'
                db.add(Experiment(
                    appeal_id=appeal.id, created_by=users['responsible'].id,
                    client_id=uuid5(ids[item['key']], 'experiment'), responsible_id=responsible.id,
                    starts_at=stamp(starts), ends_at=stamp(ends), created_at=stamp(created),
                    finished_at=stamp(finished) if finished is not None else None, **exp,
                ))
            recipients = {author.id, responsible.id} if responsible else {author.id, users['coordinator'].id}
            for recipient in recipients:
                db.add(Notification(
                    user_id=recipient, appeal_id=appeal.id, kind=item.get('notice_kind', 'received'),
                    title=item.get('notice_title', 'Обращение принято'),
                    dedupe_key=f'{namespace}:{item["key"]}:{recipient}',
                    created_at=stamp(item.get('notice_age_hours', 1)),
                    # This is historical fixture activity, never an outbound delivery.
                    telegram_attempts=5,
                ))
            if appeal.next_response_at and appeal.next_response_at < now:
                for recipient in {user.id for user in coordinators} | {responsible.id}:
                    db.add(Notification(
                        user_id=recipient, appeal_id=appeal.id, kind='overdue', title='Срок ответа истёк',
                        dedupe_key=f'overdue:{appeal.id}:{appeal.responsible_id}:{appeal.next_response_at.isoformat()}',
                        created_at=now, telegram_attempts=5,
                    ))
            print(f'MT-{appeal.id:06d} | {appeal.status} | {appeal.title}')
        print(f'Prepared {len(items)} appeals in one transaction.')


if __name__ == '__main__':
    main()
