import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDown,
  ArrowUpRight,
  ArrowRight,
  ChessKnight,
  ChessKing,
  ChessPawn,
  Globe2,
  Monitor,
  Smartphone,
  Menu,
  X,
  Mail,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Separator } from "./components/ui/separator";
import "@fontsource-variable/golos-text";
import "@fontsource-variable/geist";
import "./styles.css";

const projects = [
  {
    name: "InTechSol",
    category: "Веб-разработка",
    description:
      "Сайт металлорежущего инструмента и оснастки. Продукция и решения для промышленности.",
    url: "https://intechsol.kz/",
    domain: "intechsol.kz",
    style: "intech",
    mark: "ITS",
    subtitle: "Промышленность. В цифровом формате.",
  },
  {
    name: "Nord Auto",
    category: "Веб-разработка",
    description:
      "Сайт автозапчастей для грузовых автомобилей. Поиск нужной детали по названию и OEM-номеру.",
    url: "https://nord-auto.kz/",
    domain: "nord-auto.kz",
    style: "nord",
    mark: "NORD / AUTO",
    subtitle: "Найти деталь. Продолжить движение.",
  },
];
const telegram = ["DarthZiel", "DamirTukayev", "AlphaZeroBot02"];

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="Iron Tech — в начало">
      <svg aria-hidden="true" viewBox="0 0 32 32">
        <path d="M3 5h26v7H19v17h-7V12H3z" fill="currentColor" />
      </svg>
      <span>
        iron<span className="brand-light">tech</span>
        <span className="brand-dot">.</span>
      </span>
    </a>
  );
}

function ChessArtwork() {
  return (
    <div className="chess-art" aria-hidden="true">
      <div className="chess-board">
        {Array.from({ length: 16 }, (_, i) => (
          <span
            key={i}
            className={
              (Math.floor(i / 4) + (i % 4)) % 2 ? "square pale" : "square"
            }
          >
            {i === 6 ? (
              <ChessKnight strokeWidth={1.25} />
            ) : i === 9 ? (
              <ChessKing strokeWidth={1.25} />
            ) : i === 12 ? (
              <ChessPawn strokeWidth={1.25} />
            ) : null}
          </span>
        ))}
      </div>
      <span className="art-caption">Игра. Анализ. Развитие.</span>
    </div>
  );
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <>
      <a className="skip-link" href="#main">
        Перейти к содержимому
      </a>
      <header className="header wrap" id="top">
        <Brand />
        <nav aria-label="Основная навигация" className="desktop-nav">
          <a href="#projects">Проекты</a>
          <a href="#expertise">Что делаем</a>
          <a href="#team">О команде</a>
        </nav>
        <Button asChild variant="outline" className="header-contact">
          <a href="#contact">
            На связи <ArrowUpRight data-icon="inline-end" />
          </a>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="menu-toggle"
          aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? <X /> : <Menu />}
        </Button>
        {menuOpen && (
          <nav
            id="mobile-nav"
            className="mobile-nav"
            aria-label="Мобильная навигация"
          >
            {[
              ["projects", "Проекты"],
              ["expertise", "Что делаем"],
              ["team", "О команде"],
              ["contact", "Контакты"],
            ].map(([id, label]) => (
              <a key={id} href={`#${id}`} onClick={() => setMenuOpen(false)}>
                {label}
                <ArrowUpRight />
              </a>
            ))}
          </nav>
        )}
      </header>

      <main id="main">
        <section className="hero wrap" aria-labelledby="hero-title">
          <div className="hero-top">
            <span className="availability">
              <i /> Открыты к новым проектам
            </span>
          </div>
          <div className="hero-body">
            <h1 id="hero-title">
              Идеи становятся
              <br />
              <span>продуктами.</span>
            </h1>
            <ArrowUpRight
              className="hero-arrow"
              aria-hidden="true"
              strokeWidth={1}
            />
          </div>
          <div className="hero-bottom">
            <p>
              Разрабатываем веб-сервисы, десктопные
              <br className="desktop-break" /> и мобильные приложения.
              Продумываем детали.
              <br className="desktop-break" /> Доводим до запуска.
            </p>
            <Button asChild size="lg">
              <a href="#projects">
                Смотреть проекты <ArrowDown data-icon="inline-end" />
              </a>
            </Button>
          </div>
          <div className="platforms">
            <span>
              <Globe2 /> Веб
            </span>
            <span>
              <Monitor /> Десктоп
            </span>
            <span>
              <Smartphone /> Мобильные приложения
            </span>
            <span className="platform-note">
              Одна команда. Весь путь продукта.
            </span>
          </div>
        </section>

        <section
          className="work-section"
          id="projects"
          aria-labelledby="projects-title"
        >
          <div className="wrap">
            <div className="section-heading">
              <h2 id="projects-title">
                Работа говорит
                <br />
                за нас.
              </h2>
              <p>
                От сайтов для бизнеса до инструментов
                <br />
                для шахмат и внутренних систем.
              </p>
            </div>

            <article className="featured-project">
              <div className="feature-copy">
                <h3>
                  Chess Profi<span className="title-period">.</span>
                </h3>
                <Badge variant="outline">Десктоп · Android</Badge>
                <p>
                  Шахматы глубже,
                  <br />
                  чем следующий ход.
                </p>
                <span className="feature-detail">
                  Анализ партий, подготовка к турнирам
                  <br />и тактические задачи в одном приложении.
                </span>
                <div className="project-links">
                  <a
                    href="https://apps.microsoft.com/detail/9nmg9lqrkzq9?hl=ru-RU&gl=RU"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Microsoft Store <ArrowUpRight />
                  </a>
                  <a
                    href="https://play.google.com/store/apps/details?id=com.shv.chessprofi"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Google Play <ArrowUpRight />
                  </a>
                </div>
              </div>
              <ChessArtwork />
            </article>

            <div className="project-grid">
              {projects.map((project) => (
                <article className="project" key={project.name}>
                  <a
                    className={`project-art ${project.style}`}
                    href={project.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Открыть ${project.name}`}
                  >
                    <span className="art-top">
                      {project.domain}
                      <ArrowUpRight />
                    </span>
                    <strong>{project.mark}</strong>
                    <span className="art-bottom">{project.subtitle}</span>
                  </a>
                  <div className="project-meta">
                    <h3>
                      <a
                        href={project.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {project.name}
                        <ArrowUpRight />
                      </a>
                    </h3>
                    <span>{project.category}</span>
                  </div>
                  <p>{project.description}</p>
                </article>
              ))}
            </div>

            <article className="kazchess-project">
              <div>
                <h3>KazChessTalents</h3>
                <Badge variant="outline">Веб-платформа</Badge>
                <p>
                  Место, где растут
                  <br />
                  шахматные таланты.
                </p>
              </div>
              <div className="kazchess-description">
                <p>
                  Платформа для отслеживания прогресса шахматистов: игроки,
                  клубы, школы и рейтинги.
                </p>
                <a
                  className="text-link"
                  href="https://kazchess.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  kazchess.com <ArrowUpRight />
                </a>
              </div>
            </article>

          </div>
        </section>

        <section
          className="expertise wrap"
          id="expertise"
          aria-labelledby="expertise-title"
        >
          <div className="section-heading">
            <h2 id="expertise-title">
              Под задачу.
              <br />
              Под вашу платформу.
            </h2>
            <p>
              Выбираем технологии по тому,
              <br />
              что нужно продукту и его пользователям.
            </p>
          </div>
          <div className="service-list">
            {[
              {
                icon: Globe2,
                title: "Веб-разработка",
                text: "Корпоративные сайты, каталоги, личные кабинеты и сервисы для ежедневной работы.",
                tags: "Сайты / Веб-приложения / API",
              },
              {
                icon: Monitor,
                title: "Десктопные приложения",
                text: "Программы для компьютеров: от специализированных инструментов до внутренних систем компании.",
                tags: "Windows / Прикладное ПО",
              },
              {
                icon: Smartphone,
                title: "Мобильные приложения",
                text: "Продукты для смартфонов и Telegram Mini Apps. Нужные функции всегда под рукой.",
                tags: "Android / Telegram Mini Apps",
              },
            ].map(({ icon: Icon, title, text, tags }) => (
              <React.Fragment key={title}>
                <Separator />
                <article className="service">
                  <Icon className="service-icon" strokeWidth={1.4} />
                  <h3>{title}</h3>
                  <div>
                    <p>{text}</p>
                    <span>{tags}</span>
                  </div>
                  <ArrowUpRight className="service-arrow" aria-hidden="true" />
                </article>
              </React.Fragment>
            ))}
            <Separator />
          </div>
        </section>

        <section
          className="team-section"
          id="team"
          aria-labelledby="team-title"
        >
          <div className="wrap">
            <div className="team-top">
              <h2 id="team-title">
                Небольшая команда.
                <br />
                Личное участие.
              </h2>
              <div>
                <p>
                  Iron Tech — команда разработчиков из Павлодара. Мы объединяем
                  опыт в вебе, десктопе и мобильной разработке, чтобы создавать
                  полезные цифровые продукты.
                </p>
                <p>
                  Общаемся напрямую, разбираемся в задаче и остаёмся рядом от
                  первой идеи до запуска.
                </p>
              </div>
            </div>
            <Separator />
            <div className="partners">
              <h3>С нами сотрудничают</h3>
              <div>
                <span>
                  Филиал Казахстанской федерации шахмат
                  <br />
                  по Павлодарской области
                </span>
              </div>
            </div>
          </div>
        </section>

        <section
          className="contact wrap"
          id="contact"
          aria-labelledby="contact-title"
        >
          <div className="contact-heading">
            <h2 id="contact-title">
              Что создадим
              <br />
              <span>вместе?</span>
            </h2>
            <ArrowUpRight aria-hidden="true" strokeWidth={1} />
          </div>
          <div className="contact-bottom">
            <p>
              Расскажите об идее или задаче.
              <br />
              Начнём с разговора.
            </p>
            <div className="contact-links">
              <a className="email-link" href="mailto:studerzhan@gmail.com">
                studerzhan@gmail.com <Mail />
              </a>
              <div className="telegram-links">
                <span>Telegram</span>
                {telegram.map((name) => (
                  <a
                    key={name}
                    href={`https://t.me/${name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    @{name}
                    <ArrowUpRight />
                  </a>
                ))}
              </div>
            </div>
          </div>
        </section>
      </main>
      <footer className="footer wrap">
        <Brand />
        <span>© {new Date().getFullYear()} Iron Tech</span>
        <a href="#top">
          Наверх <ArrowRight />
        </a>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
