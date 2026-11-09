import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import {finalizePresentation,applyPresentationChartFont} from '/home/nurzhan/.codex/plugins/cache/openai-primary-runtime/presentations/26.1104.22356/skills/presentations/container_tools/artifact_tool_utils.mjs';

const workspaceDir=process.cwd();
const build=path.join(workspaceDir,'artifacts/pitch/.build');
const out=path.join(workspaceDir,'artifacts/pitch/output');
const SKILL='/home/nurzhan/.codex/plugins/cache/openai-primary-runtime/presentations/26.1104.22356/skills/presentations';
const PY='/home/nurzhan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const presentation=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#132D2A',muted:'#53675E',paper:'#F5F4EF',accent:'#AECA73',orange:'#BF4A1D'};
function txt(s,text,x,y,w,h,size=28,color=C.ink,bold=false,link){const q=s.shapes.add({geometry:'textbox',name:text.slice(0,45),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});q.text=link?[[{run:text,link:{uri:link,isExternal:true}}]]:text;q.text.style={typeface:'Arial',fontSize:size,color,bold};return q;}
function base(title,n,dark=false){const s=presentation.slides.add();s.background.fill=dark?C.ink:C.paper;txt(s,title,72,52,1136,115,44,dark?C.paper:C.ink,true);txt(s,String(n).padStart(2,'0'),1160,660,50,28,16,dark?'#BDCAC3':C.muted);return s;}
function note(s,t){s.speakerNotes.text=t;}
async function shot(s,file,x,y,w,h,crop){const bytes=await fs.readFile(path.join(workspaceDir,'artifacts/demo-video/screens',file));s.images.add({blob:bytes,contentType:'image/png',alt:'Скриншот Modus Feedback на демонстрационных данных',fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{} )});}
const gallup='https://www.gallup.com/file/workplace/704108/Employee%20Engagement%20Strategies%20for%202026.pdf';

let s=presentation.slides.add();s.background.fill=C.ink;
txt(s,'Modus Feedback',76,180,1120,130,82,C.paper,true);
txt(s,'Обратная связь сотрудников\nс понятным результатом',80,340,1090,140,42,'#D8E8B4');
txt(s,'Решение для ООО «Модус Трейд»',80,600,1100,40,22,'#BDCAC3');
note(s,'[0:00–0:20] Сотрудник первым замечает, что мешает работе. Modus Feedback помогает превратить это наблюдение в обращение с ответственным, сроком и результатом, который подтверждает сам сотрудник. Покажем это на рабочих сценариях для Модус Трейд. Примеры иллюстративные, не сведения о реальных инцидентах компании.');

s=base('Проблема начинается с обычной смены',2);
txt(s,'«Похожие коробки трудно различать.\nКаждый раз приходится уточнять»',74,205,1110,145,44,C.ink,true);
txt(s,'Сотрудник видит препятствие',76,395,510,44,27,C.orange,true);
txt(s,'Но не знает, кому написать\nи когда ждать ответа.',76,450,480,110,28);
txt(s,'Руководителю нужен результат',650,395,550,44,27,C.orange,true);
txt(s,'Кто отвечает? Какой срок?\nЧто изменилось после решения?',650,450,550,110,28);
txt(s,'Иллюстративный рабочий сценарий для Модус Трейд',76,625,1080,35,19,C.muted);
note(s,'[0:20–0:45] Представим обычную смену на складе. Похожие коробки трудно различать. Сотрудник спрашивает коллегу или пишет в чат, но сообщение само по себе не гарантирует решения. Нужны ответственный, понятный срок и проверка, стало ли лучше. Это сценарий из MVP_SPEC.md, не утверждение о реальном инциденте.');

s=base('Голос сотрудника требует внимания',3);
s.charts.add('doughnut',{position:{left:60,top:195,width:500,height:370},categories:['Полностью согласны','Остальные ответы'],series:[{name:'Доля сотрудников, %',values:[27,73],points:[{idx:0,fill:C.accent},{idx:1,fill:'#DBDFD4'}]}],hasLegend:false,doughnutOptions:{holeSize:76,firstSliceAngle:270},dataLabels:{showValue:false},chartFill:C.paper,chartLine:{fill:'none',width:0}});
txt(s,'27%',210,325,240,95,74,C.ink,true);
txt(s,'сотрудников в США полностью\nсогласны, что их мнение\nучитывают на работе',615,235,580,170,36,C.ink,true);
txt(s,'Сотруднику важно видеть,\nчто произошло с его обращением.',615,445,570,105,28);
txt(s,'Gallup, февраль 2026. Исследование США, не данные Модус Трейд.',76,600,1110,35,19,C.muted);
txt(s,'Источник: Employee Engagement Strategies for 2026, с. 2',76,635,1070,30,18,C.muted,false,gallup);
note(s,'[0:45–1:05] Gallup: в феврале 2026 года лишь 27% сотрудников США полностью соглашались, что их мнение учитывают на работе. Остальные 73% включают все другие ответы: нельзя говорить, что всех этих людей игнорируют. Мы не переносим показатель на Модус Трейд и не обещаем изменить вовлечённость одним приложением. Источник: Gallup, Employee Engagement Strategies for 2026, страница 2. '+gallup);

s=base('Полный цикл работы с обращением',4,true);
[['01','Сотрудник сообщает','Проблема или идея через сайт, бот или Mini App'],['02','Координатор назначает','У обращения появляется ответственный'],['03','Ответственный действует','Срок, уточнения, решение или эксперимент'],['04','Команда фиксирует результат','Что изменили и какие измерения получили'],['05','Автор подтверждает','Помогло: закрытие. Проблема осталась: доработка']].forEach((r,i)=>{let y=182+i*87;txt(s,r[0],76,y,65,52,32,C.accent,true);txt(s,r[1],170,y,460,48,29,C.paper,true);txt(s,r[2],650,y+3,550,68,24,'#BDCAC3');});
note(s,'[1:05–1:30] Основа продукта: единый цикл. Сотрудник отправляет обращение. Координатор назначает ответственного. Тот устанавливает срок и выполняет действие, при необходимости проверяет идею экспериментом. Результат оценивает автор. Если проблема осталась, обращение возвращается в работу. Сайт, бот и Mini App используют общие данные. Источник: MVP_SPEC.md, разделы 3–10.');

s=base('Сотруднику достаточно описать ситуацию',5);
txt(s,'Своими словами',76,202,340,65,32,C.orange,true);
txt(s,'Текст и фото\nчерез удобный канал',76,276,330,100,30);
txt(s,'ИИ помогает уточнить\nи сформулировать.',76,408,330,105,28);
txt(s,'Автор проверяет текст\nперед отправкой.',76,540,330,95,28,C.ink,true);
await shot(s,'02-form.png',435,185,780,455);
note(s,'[1:30–1:55] Сотруднику не нужно составлять служебную записку и знать ответственного. Он описывает ситуацию и при необходимости прикладывает фото. ИИ предлагает формулировку и до двух уточняющих вопросов. Исходный текст сохраняется. Применение предлагает автор, отправка без ИИ доступна. На экране фактический скриншот приложения с синтетическим обращением. Источники: MVP_SPEC.md, разделы 5–7, 9.1; artifacts/demo-video/screens/02-form.png. Реальная модель запущена по DEVELOPMENT_PROGRESS.md.');

s=base('Ответственность и сроки видны в очереди',6);
await shot(s,'05-queue.png',65,190,805,503);
txt(s,'Кто отвечает',915,215,300,55,30,C.orange,true);
txt(s,'Координатор\nназначает сотрудника.',915,280,300,90,26);
txt(s,'Когда будет ответ',915,405,300,65,30,C.orange,true);
txt(s,'Сроки и просрочки\nвидны в очереди.\nПеренос требует причины.',915,480,300,140,26);
note(s,'[1:55–2:20] Координатор видит обращения без ответственного и просрочки. Назначает человека, а ответственный фиксирует дату следующего ответа. Если срок меняется, автор видит объяснение в истории. Это создаёт проверяемый след работы. На скриншоте учебные данные: счётчики не показатели компании. Источники: MVP_SPEC.md, разделы 8, 10; artifacts/demo-video/screens/05-queue.png.');

s=base('Идею можно проверить на одной полке',7);
txt(s,'Изменение',76,200,390,45,29,C.orange,true);
txt(s,'Крупный ярлык с артикулом,\nназванием и фото товара',76,252,440,100,30,C.ink,true);
txt(s,'Небольшая проверка',76,385,440,50,29,C.orange,true);
txt(s,'Одна полка, одна смена.\nФиксируем время поиска\nи ошибки до и после.',76,445,440,145,28);
await shot(s,'09-plan.png',550,185,665,416);
txt(s,'Рабочий пример. План и критерий утверждает ответственный.',76,630,1110,35,19,C.muted);
note(s,'[2:20–2:45] Вместо изменения всего склада сразу можно проверить крупную маркировку на одной полке. Ответственный задаёт гипотезу, конкретное изменение, срок и критерий успеха. Для измерений нужны сопоставимые задания и условия. ИИ может предложить черновик, но решение принимает человек. В самом демосценарии количественная экономия не подтверждена. Источники: MVP_SPEC.md, раздел 9.2; artifacts/demo-video/screens/09-plan.png.');

s=base('Результат оценивает автор обращения',8,true);
txt(s,'«Помогло»',76,210,390,65,40,C.accent,true);
txt(s,'Обращение закрывается\nс оценкой сотрудника.',76,290,390,100,28,C.paper);
txt(s,'«Проблема осталась»',76,435,450,60,34,C.accent,true);
txt(s,'Комментарий возвращает\nобращение в работу.',76,510,410,100,28,C.paper);
await shot(s,'16-confirm.png',550,210,665,416);
note(s,'[2:45–3:10] Центральное отличие: сообщение ответственного о выполнении ещё не закрывает вопрос. Сотрудник подтверждает результат или объясняет, что проблема осталась. Тогда обращение возвращается в работу, а история сохраняется. Молчание не считается подтверждением. Это сигнал автора, не доказательство долгосрочного экономического эффекта. Источники: MVP_SPEC.md, раздел 9.3; artifacts/demo-video/screens/16-confirm.png.');

s=base('Тот же процесс помогает продажам и логистике',9);
txt(s,'Продажи',76,200,450,55,34,C.orange,true);
txt(s,'«В инструкции нет ответа\nна частый вопрос клиента»',76,275,485,115,34,C.ink,true);
txt(s,'Дополнить инструкцию.\nПроверить на нескольких обращениях.\nСпросить сотрудника, стало ли проще.',76,445,490,150,27);
txt(s,'Логистика',675,200,480,55,34,C.orange,true);
txt(s,'«Перед отгрузкой не хватает\nодного пункта проверки»',675,275,510,115,34,C.ink,true);
txt(s,'Проверить короткий чек-лист.\nСравнить возвраты на уточнение.\nЗафиксировать итог и оценку автора.',675,445,510,150,27);
txt(s,'Возможные ситуации для Модус Трейд, не отчёт о выявленных проблемах',76,630,1110,35,19,C.muted);
note(s,'[3:10–3:35] Процесс применим к разным подразделениям. В продажах сотрудник предлагает дополнить инструкцию по частому вопросу клиента. В логистике замечает недостающий пункт проверки перед отгрузкой. В обоих случаях назначаем ответственного, пробуем небольшое изменение и проверяем результат. Это предложенные нами сценарии, не подтверждённые случаи компании. Категории соответствуют MVP_SPEC.md.');

s=base('Как посчитать эффект пилота',10);
s.charts.add('bar',{position:{left:60,top:230,width:650,height:340},categories:['Условная база','Цель проверки'],series:[{name:'Часы поиска в месяц',values:[22,7.33],fill:C.ink,points:[{idx:0,fill:'#8A9C8E'},{idx:1,fill:C.accent}]}],barOptions:{direction:'column',grouping:'clustered',gapWidth:100},hasLegend:false,xAxis:{textStyle:{fontSize:22,fill:C.ink},majorGridlines:null},yAxis:{min:0,max:25,majorUnit:5,title:{text:'часы / месяц',textStyle:{fontSize:18,fill:C.muted}},textStyle:{fontSize:18,fill:C.muted},majorGridlines:{fill:'#DDE2D8',width:1}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{fontSize:24,fill:C.ink,bold:true}},chartFill:C.paper,chartLine:{fill:'none',width:0}});
txt(s,'14,7 часа',780,230,420,90,60,C.orange,true);
txt(s,'в месяц можно высвободить,\nесли время поиска снизится\nс 3 до 1 минуты',780,345,420,155,29);
txt(s,'20 поисков в день × 22 дня',780,545,420,50,24,C.muted);
txt(s,'Условная модель для одной операции. Это гипотеза, не достигнутый результат.',76,170,1110,45,21,C.orange,true);
txt(s,'Пилот должен подтвердить время поиска, частоту операций и качество комплектации.',76,630,1120,35,19,C.muted);
note(s,'[3:35–4:00] Здесь условная арифметика, а не обещание экономии. Если одна операция поиска выполняется 20 раз в день, занимает 3 минуты, а после изменения 1 минуту, при 22 рабочих днях база составляет 20×3×22÷60=22 часа. Целевое значение 20×1×22÷60=7,33 часа. Разница 14,67 часа, округляем до 14,7. Все входные значения предположительные. В пилоте нужно измерить их, проверить сопоставимость условий и отсутствие ухудшения качества. Высвобождённое время не равно сокращению денежных расходов.');

s=base('Следующий шаг: пилот в одном подразделении',11);
txt(s,'Предлагаем согласовать',76,195,540,55,32,C.orange,true);
txt(s,'Одно подразделение\nОдин координатор\nКороткий период проверки',76,275,530,190,36,C.ink,true);
txt(s,'Что измеряем',700,195,490,55,32,C.orange,true);
txt(s,'Время до первого ответа\nДолю просроченных обращений\nДолю подтверждённых решений\nЭффект конкретных изменений',700,275,490,230,28);
txt(s,'Веб-цикл реализован. Бот и модель запущены.\nФинальная проверка Mini App на телефоне остаётся перед показом.',76,565,1100,80,23,C.muted);
note(s,'[4:00–4:25] Следующий шаг предлагаем согласовать с заказчиком: одно подразделение, координатор и короткий период проверки. До старта определим базу и метрики. Доля подтверждённых решений должна считаться по согласованной когорте и сроку наблюдения, чтобы свежие обращения не искажали показатель. По DEVELOPMENT_PROGRESS.md веб-цикл реализован, реальная модель и бот запущены, финальная проверка Telegram и Mini App на личном телефоне ещё остаётся. Пилот и его сроки пока предложение, не договорённость.');

s=base('Команда с опытом создания продуктов',12,true);
txt(s,'Проекты участников команды',76,175,1080,45,26,'#BDCAC3');
txt(s,'KazChessTalents',76,245,530,60,38,C.accent,true,'https://kazchess.com/');
txt(s,'Шахматная платформа\nkazchess.com',76,315,530,90,25,C.paper,false,'https://kazchess.com/');
txt(s,'Chess Profi',700,245,500,60,38,C.accent,true,'https://apps.microsoft.com/detail/9nmg9lqrkzq9?hl=ru-RU&gl=RU');
txt(s,'Приложение в Microsoft Store\nОткрыть страницу приложения',700,315,500,90,25,C.paper,false,'https://apps.microsoft.com/detail/9nmg9lqrkzq9?hl=ru-RU&gl=RU');
txt(s,'Водоканал Павлодара',76,445,570,55,34,C.accent,true);
txt(s,'Внутренняя система',76,510,530,50,25,C.paper);
txt(s,'InTechSol',700,445,500,55,38,C.accent,true,'https://intechsol.kz/');
txt(s,'Сайт компании\nintechsol.kz',700,510,500,85,25,C.paper,false,'https://intechsol.kz/');
txt(s,'Готовы вместе провести пилот и согласовать дальнейшее сопровождение',76,625,1110,40,23,C.paper,true);
note(s,'[4:25–5:00] Наш аргумент в пользу команды: у её участников есть опыт создания продуктов. Представляем KazChessTalents, внутреннюю систему Водоканала Павлодара, Chess Profi в Microsoft Store и сайт InTechSol. Готовы вместе с Модус Трейд провести пилот, собрать обратную связь и согласовать дальнейшее сопровождение. На вопросы о проектах каждый участник называет свой реальный вклад. Портфолио и участие команды предоставлены пользователем, независимо авторство не подтверждалось. Публичные источники: https://kazchess.com/ ; https://apps.microsoft.com/detail/9nmg9lqrkzq9?hl=ru-RU&gl=RU ; https://intechsol.kz/ . Для внутренней системы публичная ссылка не предоставлена, описание, заказчик, метрики и изображения не выдумывались. Имена участников и объём поддержки не заданы.');

for(const slide of presentation.slides.items) for(const chart of slide.charts.items) applyPresentationChartFont(chart,{fontFamily:'Arial'});
await fs.mkdir(build,{recursive:true});await fs.mkdir(out,{recursive:true});
await fs.writeFile(path.join(build,'speaker-notes.txt'),presentation.slides.items.map((s,i)=>`Слайд ${i+1}\n${s.speakerNotes.text}`).join('\n\n'));
for (const [i,slide] of presentation.slides.items.entries()){
  const blob=await presentation.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
  console.log('rendered',i+1);
}
const candidatePath=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const result=await finalizePresentation({workspaceDir,candidatePath,finalPath:path.join(out,'Modus-Feedback-Pitch.pptx'),pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],requiredNativeChartOwnerSlides:[3,10],requiredNativeTableOwnerSlides:[],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));
