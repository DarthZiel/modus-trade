---
name: "Iron Tech"
description: "Editorial portfolio for a Pavlodar software team."
colors:
  background: "#f5f5f0"
  foreground: "#202321"
  primary: "#2454e8"
  primary-foreground: "#ffffff"
  secondary: "#e9eae3"
  muted-foreground: "#62665f"
  border: "#d5d7ce"
  available: "#3e7352"
  body-muted: "#595e56"
  portfolio: "#1d231f"
  portfolio-border: "#50584f"
  portfolio-muted: "#b7c0b7"
  chess-paper: "#d9e8cf"
  chess-ink: "#253625"
  chess-border: "#7b8b70"
  chess-accent: "#5f7c4f"
  chess-muted: "#52614a"
  chess-board-bg: "#c4d7b6"
  chess-square: "#718b5e"
  chess-square-pale: "#e8efdd"
  chess-piece: "#263c25"
  chess-caption: "#435637"
  intech-paper: "#e4e5df"
  intech-ink: "#2c332e"
  intech-orange: "#d77530"
  nord-blue: "#294bbb"
  nord-paper: "#f0f3ff"
  kazchess-gold: "#e0a549"
  kazchess-ink: "#342819"
  kazchess-border: "#89652c"
  water-paper: "#dbe5e7"
  water-ink: "#284650"
  water-mark: "#9ebac0"
  feedback-paper: "#f1eee8"
  feedback-ink: "#252923"
  feedback-rust: "#b8421b"
  feedback-badge: "#e1ddd4"
  feedback-badge-ink: "#424238"
  service-arrow: "#858a80"
  team-copy: "#53594f"
  chess-shadow: "#24302125"
  menu-shadow: "#20232114"
typography:
  display:
    fontFamily: "Golos Text Variable, sans-serif"
    fontSize: "clamp(52px, 6.8vw, 96px)"
    fontWeight: 550
    lineHeight: 1.06
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Golos Text Variable, sans-serif"
    fontSize: "clamp(36px, 4.1vw, 58px)"
    fontWeight: 500
    lineHeight: 1.13
    letterSpacing: "-0.035em"
  body:
    fontFamily: "Golos Text Variable, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Golos Text Variable, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  latin-title:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "clamp(40px, 4.1vw, 60px)"
    fontWeight: 550
    letterSpacing: "-0.04em"
rounded:
  badge: "5px"
  button: "6px"
  base: "8px"
  panel: "12px"
  water-mark: "20px"
spacing:
  8: "8px"
  12: "12px"
  16: "16px"
  20: "20px"
  22: "22px"
  24: "24px"
  28: "28px"
  32: "32px"
  40: "40px"
  42: "42px"
  48: "48px"
  64: "64px"
  72: "72px"
  80: "80px"
  96: "96px"
  100: "100px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.button}"
    height: "54px"
    padding: "0 25px"
  button-outline:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.button}"
    size: "44px"
  badge-chess:
    textColor: "{colors.chess-ink}"
    rounded: "{rounded.badge}"
    height: "25px"
    padding: "0 10px"
  project-cover:
    rounded: "{rounded.panel}"
    height: "285px"
    padding: "28px"
  navigation:
    textColor: "{colors.foreground}"
---

# Design System: Iron Tech

## Overview

**Creative North Star: "The Editorial Project Catalogue"**

A warm-paper editorial portfolio: large Cyrillic typography, charcoal work galleries and precise blue wayfinding. The IT mark and directional arrows connect the company identity, project selection and contact invitation.

Project covers retain their own restrained palettes. They are graphic interpretations, not product screenshots. This standalone site has its own design system, independent of the Modus Feedback application.

**Key Characteristics:**
- Large, compact headlines and generous section spacing.
- Flat surfaces, quiet rules and distinct project cover colors.
- Golos for Cyrillic; Geist reserved for Latin identity and cover titles.

## Colors

Primary blue (`primary`) directs attention to actions, arrows and emphasized headline words. Warm paper (`background`), charcoal ink (`foreground`) and soft gray-green (`secondary`) define the company surfaces. The portfolio switches to deep charcoal (`portfolio`) with paper text and sage-gray descriptions.

Project-specific tokens are intentional: sage greens for Chess Profi, industrial paper and orange for Intech, cobalt for Nord Auto, ochre for KazChessTalents, blue-gray for the water utility and warm paper with rust for Feedback. Keep those colors inside their respective covers. All observed hues, supporting text colors, borders and translucent shadow colors are recorded in the frontmatter.

## Typography

Golos Text Variable with sans-serif fallback is the primary family. Geist Variable with sans-serif fallback is deliberately limited to the Latin wordmark and Latin project cover headings; project metadata and Russian copy use Golos.

Display: 550 weight, 1.06 line height, −0.04em tracking; mobile uses `clamp(40px, 8.7vw, 64px)`. Section headlines: 500 weight, 1.13 line height; mobile 36px. Body sizes range from 13px project descriptions to 17px hero copy with 1.65–1.8 line height. Labels are typically 11–12px. Project descriptions stay within 48ch, service copy within 45ch. The contact heading has its own 48–84px scale (52px mobile).

## Layout

The centered container is at most 1440px including horizontal padding: 64px desktop, 40px at ≤1100px and 22px at ≤760px. Project grids and the featured project use two equal columns; mobile stacks them. Service rows combine icon, title, description and arrow; mobile moves descriptions below titles and removes the decorative final arrow. Team and contact layouts stack on mobile. Desktop project gaps are 40px, tablet 28px, mobile 32px.

The header is 112px high, 84px mobile. Desktop navigation becomes a 44px menu button with an anchored dropdown at ≤760px. Above 1500px the hero gains extra top spacing. Sections use generous 48–100px vertical padding rather than repeated boxed cards.

## Elevation & Depth

Flat tonal layering carries the page. Only the decorative chessboard (`0 18px 35px #24302125`) and mobile navigation (`0 16px 32px #20232114`) have shadows. Borders separate services and contacts; project art supplies contrast without elevated card shells.

## Shapes

Project panels and mobile navigation use 12px corners. Main buttons use 6px corners, the base component radius is 8px, and the Chess badge uses 5px. Water artwork uses 20px rounded bars; the availability dot is circular. Thin rules and outlined badges complement broad rectangular covers.

## Components

- **Buttons:** blue primary with white text; hero 54px high, 25px horizontal padding (48px / 20px mobile). Header action and outlined mobile toggle are 44px. Primary hover uses 80% primary color; active scales to .97. Focus remains visible.
- **Navigation:** quiet 14px desktop links, 16px mobile dropdown links. Mouse hover underlines links; the mobile disclosure reflects expanded state and closes after navigation.
- **Badges:** compact 25px labels. Outlined project badges inherit local ink and border colors; Feedback uses its own filled neutral badge. Noninteractive labels do not gain invented states.
- **Project covers:** 285px desktop / 260px mobile for external linked projects, 250px / 240px for secondary artwork. Linked covers brighten to 1.07 on fine-pointer hover; metadata links underline. Chess artwork is a decorative rotated board, not a live interface.
- **Service rows:** open grid with thin dividers, blue line icons and plain text. Contacts use a prominent email link and wrapping Telegram links; there are no form fields.

Buttons use a 140ms cubic-bezier(.23, 1, .32, 1) transform response and 160ms color transition. The hero arrow enters once over 650ms using the same curve; linked covers use 180ms brightness transitions. Global focus is a 3px blue outline offset 5px. Reduced motion removes animation, transitions, active scaling and smooth scrolling.

## Do's and Don'ts

### Do:
- Do preserve the warm-paper / charcoal section rhythm.
- Do use Golos Text for Russian copy and Geist only for Latin wordmarks and project cover titles.
- Do retain visible keyboard focus and reduced-motion behavior.

### Don't:
- Don't replace the distinct project cover palettes with one generic brand color.
- Don't present decorative covers as application screenshots.
- Don't add ambient shadows or continuous animation to flat content sections.
