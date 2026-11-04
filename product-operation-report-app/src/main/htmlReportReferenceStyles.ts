/** Visual treatment based on the user's six-module report reference.
 * Keep analysis, evidence disclosures and offline interactions unchanged. */
export function renderReferenceReportStyles(): string {
  return `
  body[data-report-format="modules"] {
    --paper: #faf8f5; --paper-alt: #f8f3ee; --surface: #fff;
    --ink: #332b26; --ink-soft: #625b55; --muted: #776f66;
    --line: #eadfd5; --line-strong: #d9c6b7;
    --accent: #bc6845; --accent-strong: #985034; --accent-soft: #fff1e6;
    --radius: 18px; --font-display: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    --font-body: "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    --content-pad: clamp(24px, 3.4vw, 48px);
    --page-shadow: 0 8px 32px rgb(77 49 26 / .045);
    font-size: 15px; line-height: 1.85;
  }
  body[data-report-format="modules"] .report-masthead,
  body[data-report-format="modules"] .toc { display: none; }
  body[data-report-format="modules"] .shell { display: block; width: min(1120px, calc(100% - 64px)); margin: 40px auto 64px; }
  body[data-report-format="modules"] .report { overflow: visible; background: transparent; border: 0; box-shadow: none; }
  body[data-report-format="modules"] .report-body { padding: 0; }
  body[data-report-format="modules"] .reference-cover { padding: 36px; background: #fff; border: 1px solid #edd6c3; border-radius: 22px; box-shadow: 0 3px 4px rgb(65 40 20 / .035), 0 12px 28px rgb(65 40 20 / .035); }
  .reference-eyebrow { margin: 0 0 12px; color: #ad6244; font-size: 13px; font-weight: 700; }
  .reference-cover h1 { margin: 0; font-size: 32px; line-height: 1.3; font-weight: 800; letter-spacing: -.035em; }
  .reference-subtitle { margin: 12px 0 26px; color: #81756a; font-size: 15px; }
  .reference-summary { padding: 24px; background: linear-gradient(120deg, #eef8f1, #f3eefc); border: 1px solid #e8ddfa; border-radius: 18px; }
  .reference-summary h2 { margin: 0 0 20px; font-size: 23px; font-weight: 800; }
  .reference-summary h2 span { color: #ce754d; }
  .reference-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .reference-summary-card { display: block; min-width: 0; padding: 18px 16px; color: var(--ink); text-decoration: none; background: rgb(255 255 255 / .88); border: 1px solid #eaded2; border-radius: 12px; transition: box-shadow .15s; }
  .reference-summary-card:nth-child(3n+2) { border-color: #c9e4d6; }
  .reference-summary-card:nth-child(3n) { border-color: #f0d5ae; }
  .reference-summary-card:hover { box-shadow: 0 5px 16px rgb(70 50 30 / .07); }
  .reference-summary-card > span { display: block; margin-bottom: 10px; color: #ad6244; font-size: 12px; font-weight: 700; }
  .reference-summary-card > strong { display: block; font-size: 16px; line-height: 1.65; }
  .reference-summary-card p { margin: 6px 0 0; color: #71685f; font-size: 13px; line-height: 1.75; }
  .reference-footnote { margin: 14px 0 0; color: #81756a; font-size: 12px; line-height: 1.7; }
  body[data-report-format="modules"] .report-section { padding: 0 32px 32px; margin: 32px 0; background: #fff; border: 1px solid #eadfd5; border-radius: 18px; box-shadow: 0 6px 22px rgb(65 40 20 / .035); }
  body[data-report-format="modules"] .reference-module-intro { margin: 0 0 30px; overflow: hidden; border: 1px solid var(--accent); border-radius: 15px; background: var(--accent-soft); box-shadow: 0 9px 18px rgb(65 40 20 / .06); }
  .reference-module-intro > header { padding: 20px 24px; background: var(--accent); color: #fff; }
  .reference-module-intro > header > span { display: inline-block; padding: 4px 10px; background: rgb(255 255 255 / .2); border-radius: 4px; font-size: 12px; font-weight: 700; }
  body[data-report-format="modules"] .reference-module-intro > header > h3 { margin: 10px 0 6px; color: #fff; font-size: 23px; font-weight: 750; line-height: 1.5; }
  body[data-report-format="modules"] .reference-module-intro > header > p { margin: 0; max-width: none; color: #fff; font-size: 14px; line-height: 1.8; }
  .reference-intro-body { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 24px; padding: 22px 24px; }
  body[data-report-format="modules"] .reference-intro-body h4 { margin: 0 0 8px; color: var(--accent-strong); font-size: 15px; font-weight: 750; }
  body[data-report-format="modules"] .reference-intro-body p { margin: 0 0 16px; color: #62574f; font-size: 13px; line-height: 1.85; }
  .reference-intro-actions ol { margin: 0; padding-left: 19px; color: #62574f; font-size: 13px; line-height: 1.85; }
  .reference-intro-actions li { margin: 5px 0; padding-left: 3px; }
  .reference-intro-deliverables { display: grid; gap: 12px; }
  .reference-intro-deliverables > section { display: flex; flex-direction: column; justify-content: center; padding: 18px; border: 1px solid color-mix(in srgb, var(--accent) 65%, white); border-radius: 9px; background: #fff; }
  body[data-report-format="modules"] .reference-intro-deliverables p { margin: 0; }
  .reference-gender-overview { margin: 0 0 24px; padding: 24px; border: 1px solid #bfe3cf; border-radius: 16px; background: linear-gradient(120deg, #f2faf5, #fff); }
  body[data-report-format="modules"] .reference-gender-overview h3 { margin: 4px 0 6px; color: #285e44; font-size: 21px; }
  body[data-report-format="modules"] .reference-gender-overview > p { margin: 0 0 20px; color: #718378; font-size: 13px; }
  .reference-gender-overview .reference-eyebrow { color: #3b8764; font-size: 12px; }
  .reference-gender-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .reference-gender-grid article { padding: 18px 10px; border: 1px solid #d6e9de; border-radius: 14px; background: #fff; text-align: center; }
  body[data-report-format="modules"] .reference-gender-grid h4 { display: flex; align-items: center; justify-content: center; min-height: 64px; margin: 0 0 16px; font-size: 16px; line-height: 1.6; }
  .reference-gender-ring { display: grid; place-items: center; width: 136px; height: 136px; margin: auto; border-radius: 50%; background: conic-gradient(#60a57f 0 var(--female-share), #eaa07d var(--female-share) 100%); }
  .reference-gender-ring > div { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 103px; height: 103px; border-radius: 50%; background: #fff; }
  .reference-gender-ring strong { color: #297052; font: 750 23px/1.4 var(--font-data); }
  .reference-gender-ring span { color: #78877e; font-size: 13px; }
  body[data-report-format="modules"] .reference-gender-grid p { margin: 15px 0 0; color: #6f7872; font-size: 11px; }
  .reference-gender-grid p span { color: #60a57f; }
  .reference-gender-grid p i { color: #eaa07d; font-style: normal; }
  .reference-audience-strategies { margin: 28px 0; }
  .reference-audience-strategies > article { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.9fr); align-items: start; gap: 24px; padding: 22px; margin-bottom: 14px; border: 1px solid #e1d6f4; border-radius: 14px; background: #f8f5fe; }
  .reference-audience-strategies > article:nth-of-type(even) { background: #eef9f4; border-color: #c6e9d8; }
  .reference-audience-rank { display: inline-block; margin-bottom: 10px; padding: 3px 9px; border-radius: 5px; background: #e9dff9; color: #71569c; font-size: 12px; font-weight: 700; }
  .reference-audience-strategies strong { display: block; font-size: 15px; }
  body[data-report-format="modules"] .reference-audience-strategies h4 { margin: 0 0 8px; color: #705299; font-size: 17px; }
  body[data-report-format="modules"] .reference-audience-strategies p { margin: 7px 0; font-size: 15px; line-height: 1.8; }
  .reference-audience-name { color: #282421; font-weight: 750; line-height: 1.65; }
  .reference-audience-traits.reference-audience-traits--compact { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 7px; margin-top: 12px; }
  .reference-audience-traits--compact .audience-trait-tag { font-weight: 700; padding: 4px 8px; font-size: 12px; }
  .reference-audience-traits--compact [data-trait-color="1"] { background: #fff0d6; color: #94631b; }
  .reference-audience-traits--compact [data-trait-color="2"] { background: #ddf2e7; color: #327456; }
  .reference-audience-sources { display: block; margin-top: 10px; line-height: 1.6; }
  .reference-audience-traits { display: grid; gap: 12px; margin-top: 14px; }
  .audience-trait-group { min-width: 0; }
  .audience-trait-source { display: block; margin-bottom: 5px; color: #756b63; font-size: 11px; font-weight: 600; }
  .audience-trait-tags { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 6px; }
  .audience-trait-tag { display: inline-flex; align-items: baseline; gap: 5px; max-width: 100%; padding: 4px 8px; border-radius: 5px; background: #e6efff; color: #3d6395; font-size: 12px; line-height: 1.7; }
  .audience-trait-tag b { font-weight: 750; white-space: nowrap; }
  .audience-trait-group:nth-child(3n+2) .audience-trait-tag { background: #fff0d6; color: #94631b; }
  .audience-trait-group:nth-child(3n) .audience-trait-tag { background: #ddf2e7; color: #327456; }
  .audience-trait-note { color: #756b63; font-size: 12px; line-height: 1.75; }
  body[data-report-format="modules"] .reference-audience-copy h4 { margin-bottom: 10px; font-size: 19px; font-weight: 750; }
  body[data-report-format="modules"] .reference-audience-copy p { margin: 0 0 12px; color: #282421; font-size: 17px; font-weight: 750; line-height: 1.75; }
  .reference-audience-copy .strategy-emphasis { display: inline; color: #282421; font-size: inherit; font-weight: 750; }
  .reference-audience-copy > small { display: block; margin-top: 12px; line-height: 1.65; }
  .reference-audience-strategies small { color: #887c71; font-size: 11px; }
  body[data-report-format="modules"] .report-section[data-section="M1"] { --accent: #c96f48; --accent-strong: #a45231; --accent-soft: #fff1e6; --line: #f0ddcd; }
  body[data-report-format="modules"] .report-section[data-section="M2"] { --accent: #3f8b69; --accent-strong: #286d4d; --accent-soft: #eaf7ef; --line: #cfe8da; }
  body[data-report-format="modules"] .report-section[data-section="M3"] { --accent: #5887b8; --accent-strong: #386697; --accent-soft: #edf5fc; --line: #d4e3f1; }
  body[data-report-format="modules"] .report-section[data-section="M4"] { --accent: #b57b29; --accent-strong: #91601d; --accent-soft: #fff5df; --line: #efdfbc; }
  body[data-report-format="modules"] .report-section[data-section="M5"] { --accent: #8263b1; --accent-strong: #6b4b95; --accent-soft: #f3edfc; --line: #e2d6f0; }
  body[data-report-format="modules"] .report-section[data-section="M6"] { --accent: #c46570; --accent-strong: #a04a59; --accent-soft: #fceef1; --line: #f0d6dc; }
  body[data-report-format="modules"] .report-section { --paper-alt: var(--accent-soft); --series-1: var(--accent); --series-2: #e9a17f; --series-3: #91bcac; --series-4: #a397bb; }
  body[data-report-format="modules"] .report-section > h2 { max-width: none; padding: 18px 22px; margin: 0 -32px 28px; background: var(--accent-soft); border-left: 4px solid var(--accent); border-radius: 0 18px 0 0; font-size: 23px; font-weight: 750; }
  body[data-report-format="modules"] .visual-block > figcaption { display: inline-block; padding: 5px 12px; margin-bottom: 18px; border-radius: 6px; background: var(--accent-soft); color: var(--accent-strong); font-size: 13px; }
  body[data-report-format="modules"] .visual-note { font-size: 12px; }
  body[data-report-format="modules"] .fact-grid { gap: 12px; border: 0; }
  body[data-report-format="modules"] .fact-item { min-height: 0; padding: 20px; gap: 10px; background: #fffbf7; border: 1px solid var(--line); border-radius: 12px; }
  body[data-report-format="modules"] .fact-item span { font-size: 12px; color: var(--accent-strong); }
  body[data-report-format="modules"] .fact-item strong { font-size: 14px; font-weight: 600; }
  body[data-report-format="modules"] .fact-item.reference-fact { display: grid; grid-template-columns: 132px minmax(0, 1fr); align-items: start; gap: 16px; padding: 20px; }
  .reference-fact > header { display: flex; gap: 12px; align-items: baseline; margin: 0; padding: 2px 0; border: 0; }
  body[data-report-format="modules"] .reference-fact > header > b { flex-shrink: 0; color: #b36846; font: 600 11px/1.6 var(--font-data); }
  body[data-report-format="modules"] .reference-fact h4 { margin: 0; font-size: 13px; line-height: 1.8; font-weight: 600; color: #a45f3e; }
  body[data-report-format="modules"] .reference-fact p.reference-fact-value { max-width: none; margin: 0; color: #24211e; font-size: 16px; font-weight: 750; line-height: 1.7; }
  body[data-report-format="modules"] .reference-fact-value strong { display: inline; color: inherit; font-size: inherit; font-weight: inherit; }
  body[data-report-format="modules"] .profile-panel { padding: 22px; border-radius: 14px; box-shadow: 0 3px 12px rgb(45 70 51 / .035); }
  body[data-report-format="modules"] .profile-panel__head { display: grid; grid-template-columns: 30px minmax(0, 1fr); align-items: center; gap: 8px; padding: 12px; border: 0; border-radius: 8px; background: var(--accent-soft); }
  body[data-report-format="modules"] .profile-panel__head h3 { color: var(--accent-strong); font-size: 16px; font-weight: 750; line-height: 1.55; }
  body[data-report-format="modules"] .profile-facets { gap: 0; }
  body[data-report-format="modules"] .profile-facets .bar-facet { padding: 20px 0 12px; border-bottom: 1px dashed #e3e9e4; }
  body[data-report-format="modules"] .profile-facets .bar-facet:last-child { padding-bottom: 0; border: 0; }
  body[data-report-format="modules"] .bar-label { font-size: 13px; }
  body[data-report-format="modules"] .bar-label strong { color: var(--accent-strong); font-size: 13px; font-weight: 750; }
  body[data-report-format="modules"] .bar-facet h4 { margin: 0 0 16px; color: #3f3933; font-size: 15px; font-weight: 750; }
  body[data-report-format="modules"] .bar-track { height: 7px; }
  body[data-report-format="modules"] .donut-card { border: 1px solid var(--line); border-radius: 14px; background: #fff; }
  body[data-report-format="modules"] .method-playbooks { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  body[data-report-format="modules"] .method-playbook > header { border: 0; padding: 0 0 12px; }
  body[data-report-format="modules"] .method-playbook > header span { font-size: 17px; }
  body[data-report-format="modules"] .method-playbook > header strong { font-size: 12px; }
  body[data-report-format="modules"] .material-card-list { grid-template-columns: minmax(0, 1fr); gap: 12px; background: transparent; }
  body[data-report-format="modules"] .material-card { padding: 22px; border: 1px solid #e7e0f0; border-radius: 12px; background: #faf8fd; }
  body[data-report-format="modules"] .material-card p { font-size: 14px; line-height: 1.85; }
  body[data-report-format="modules"] .material-card > header strong { font-size: 16px; }
  body[data-report-format="modules"] .selling-item { padding: 24px; border: 1px solid var(--line); border-radius: 12px; background: #fffbf4; }
  body[data-report-format="modules"] .selling-item p { font-size: 14px; }
  body[data-report-format="modules"] .ordinal-item { padding: 18px; margin-bottom: 10px; border: 1px solid var(--line); border-radius: 10px; background: #fffbf4; }
  body[data-report-format="modules"] .ordinal-item:nth-child(-n+3) { background: var(--accent-soft); }
  body[data-report-format="modules"] .voc-group { padding: 24px; border-radius: 14px; background: #faf8fc; }
  body[data-report-format="modules"] .voc-group > header strong { color: var(--accent-strong); }
  body[data-report-format="modules"] .voc-item blockquote { padding: 12px 16px; border-radius: 6px; background: #fff; font-size: 14px; }
  body[data-report-format="modules"] .report-section[data-section="M5"] > h3 { padding: 18px 22px 12px; margin: 20px 0 0; border: 1px solid var(--line); border-bottom: 0; border-radius: 12px 12px 0 0; background: var(--accent-soft); color: var(--accent-strong); font-size: 17px; }
  body[data-report-format="modules"] .report-section[data-section="M5"] > h3 + p { max-width: none; padding: 8px 22px 22px; margin: 0 0 20px; border: 1px solid var(--line); border-top: 0; border-radius: 0 0 12px 12px; background: var(--accent-soft); font-size: 14px; }
  body[data-report-format="modules"] .audience-route { --route-color: #7653b0; display: block; padding: 24px; border-radius: 14px; background: var(--route-bg, #f1ebff); border-color: var(--route-line, #dcccfa); }
  body[data-report-format="modules"] .audience-route > header { display: flex; gap: 10px; align-items: baseline; margin-bottom: 12px; }
  body[data-report-format="modules"] .audience-route > header strong { font-size: 17px; font-weight: 750; color: var(--route-color); }
  body[data-report-format="modules"] .audience-route__path { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  body[data-report-format="modules"] .audience-route__path > div { display: flex; align-items: baseline; gap: 8px; padding: 7px 12px; }
  body[data-report-format="modules"] .audience-route__path p { margin: 0; font-size: 14px; font-weight: 650; }
  body[data-report-format="modules"] .audience-route__path small { color: var(--route-color); font-size: 12px; font-weight: 700; }
  body[data-report-format="modules"] .audience-route .route-arrow { transform: none; }
  body[data-report-format="modules"] .audience-route:nth-child(5n+2) { --route-bg: #fff6d9; --route-line: #efdc9d; --route-color: #a76e12; }
  body[data-report-format="modules"] .audience-route:nth-child(5n+3) { --route-bg: #e6f6ee; --route-line: #c3e8d7; --route-color: #287d5d; }
  body[data-report-format="modules"] .audience-route:nth-child(5n+4) { --route-bg: #fcecf3; --route-line: #efd2df; --route-color: #b34b80; }
  body[data-report-format="modules"] .audience-route:nth-child(5n+5) { --route-bg: #eaf3ff; --route-line: #cbdef4; --route-color: #356fa8; }
  body[data-report-format="modules"] .audience-route__path > div, body[data-report-format="modules"] .audience-route__path > div:last-child { background: rgb(255 255 255 / .8); }
  body[data-report-format="modules"] .audience-evidence span { font-size: 12px; }
  body[data-report-format="modules"] .material-insight-cloud.keyword-panel { padding: 28px; border-color: var(--line); background: #fffcf6; }
  body[data-report-format="modules"] .material-insight-words.word-cloud { background: linear-gradient(120deg, #fbefe4, #fcfaf6); border-radius: 12px; }
  body[data-report-format="modules"] .evidence-disclosure summary { padding: 16px 18px; font-size: 13px; background: #fffcf9; }
  .reference-material-samples { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; padding: 16px 18px; margin: 0 0 26px; border-radius: 12px; background: #eef7fb; }
  .reference-material-samples > b { color: #3b4147; font-size: 15px; }
  .reference-material-counts { display: flex; flex-wrap: wrap; gap: 10px; margin: 0; }
  .reference-material-counts > div { display: flex; align-items: baseline; gap: 6px; padding: 7px 12px; border: 0; border-radius: 8px; background: #fff; }
  .reference-material-counts span { font-size: 14px; font-weight: 500; }
  .reference-material-counts strong { color: #34312f; font: 750 18px/1.3 var(--font-data); }
  .reference-material-counts small { font-size: 14px; }
  .reference-material-scope { flex: 1 1 420px; }
  body[data-report-format="modules"] .reference-material-scope p { display: inline; margin: 0 10px 0 0; max-width: none; color: #75818a; font-size: 11px; line-height: 1.8; }
  body[data-report-format="modules"] .material-card { display: block; padding: 22px 24px; }
  body[data-report-format="modules"] .material-card > header { display: flex; gap: 10px; align-items: baseline; margin-bottom: 12px; }
  body[data-report-format="modules"] .material-card > header .reference-material-dot { font-size: 9px; }
  body[data-report-format="modules"] .material-card > header strong { color: #34323e; font-size: 17px; font-weight: 750; }
  .reference-material-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
  .reference-material-tags > span { max-width: 100%; padding: 4px 8px; border-radius: 5px; font-size: 11px; font-weight: 650; line-height: 1.8; }
  .reference-material-tags b { font-weight: 750; margin-right: 5px; }
  .material-framework { background: #e8efff; color: #436ca6; }
  .material-basis { background: #fff0ce; color: #986521; }
  .material-audience { background: #e1f4e9; color: #327353; }
  body[data-report-format="modules"] .material-card p.reference-material-advice { max-width: none; margin: 8px 0 0; color: #625b61; font-size: 14px; line-height: 1.85; }
  .reference-material-advice b, .reference-material-advice strong { color: #36313b; font-weight: 750; }
  body[data-report-format="modules"] .reference-selling-groups > figcaption { display: block; background: none; padding: 0; font-size: 22px; color: #44382d; font-weight: 750; }
  .reference-needs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
  .reference-need-group { --need-accent: #8961bd; --need-bg: #eee5fb; padding: 22px; border-radius: 14px; background: #faf8f8; border: 0; }
  .reference-need-group[data-need-color="1"] { --need-accent: #568cc2; --need-bg: #e4f0fc; }
  .reference-need-group[data-need-color="2"] { --need-accent: #3c9c78; --need-bg: #def5e9; }
  .reference-need-group[data-need-color="3"] { --need-accent: #c36397; --need-bg: #fbe5f0; }
  body[data-report-format="modules"] .reference-need-group h4 { display: inline-block; margin: 0 0 18px; padding: 5px 12px; background: var(--need-bg); color: #51464b; border-radius: 20px; font-size: 15px; font-weight: 750; }
  .reference-need-group ul { list-style: none; margin: 0; padding: 0; }
  .reference-need-group li { display: flex; align-items: baseline; gap: 10px; margin: 0 0 17px; padding: 0; }
  .reference-need-group li:last-child { margin-bottom: 0; }
  .reference-need-group li > span { flex: 0 0 17px; text-align: center; border-radius: 50%; color: #fff; background: var(--need-accent); font: 700 12px/17px var(--font-body); }
  .reference-need-group strong { color: #3f3738; font-size: 16px; font-weight: 750; }
  .reference-need-benefit { color: #625b55; font-size: 14px; line-height: 1.85; }
  .reference-need-benefit > span { color: #a79a8e; margin: 0 4px; }
  .reference-need-index { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .reference-need-index a { display: inline-block; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 700; text-decoration: none; }
  .reference-need-index a[data-need-color="0"] { color: #8055b9; background: #eee5fb; }
  .reference-need-index a[data-need-color="1"] { color: #4d80b5; background: #e4f0fc; }
  .reference-need-index a[data-need-color="2"] { color: #298564; background: #def5e9; }
  .reference-need-index a[data-need-color="3"] { color: #b34b80; background: #fbe5f0; }
  .reference-section-number { color: #c57048; margin-right: 5px; }
  body[data-report-format="modules"] .selling-strategy-visual { gap: 24px; margin-bottom: 24px; }
  body[data-report-format="modules"] .reference-selling-groups, body[data-report-format="modules"] .ordinal-visual:has(.reference-ranking-grid) { padding: 24px; margin: 0; border: 1px solid #eadfd5; border-radius: 16px; background: #fff; }
  body[data-report-format="modules"] .reference-ranking-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  body[data-report-format="modules"] .reference-ranking-grid .ordinal-item { display: block; padding: 16px 14px; margin: 0; background: #fffaf4; border: 1px solid #edddcc; }
  body[data-report-format="modules"] .reference-ranking-grid .ordinal-item > span { display: block; margin-bottom: 8px; font-size: 12px; font-weight: 750; color: #c57048; }
  .reference-ranking-grid strong { display: block; font-size: 16px; font-weight: 750; line-height: 1.6; }
  body[data-report-format="modules"] .reference-ranking-grid p { color: #776f66; font-size: 12px; line-height: 1.7; margin: 8px 0 0; }
  .reference-ranking-grid small { display: block; color: #8a7766; font-size: 11px; }
  body[data-report-format="modules"] .reference-ranking-intro { margin: 0 0 18px; }
  body[data-report-format="modules"] .ordinal-visual:has(.reference-ranking-grid) > figcaption { display: block; padding: 0; background: none; font-size: 22px; font-weight: 750; color: #44382d; }
  .material-insight-cloud .cloud-explorer { display: block; }
  .material-insight-words.word-cloud.packed-word-cloud { container-type: inline-size; position: relative; display: block; width: 100%; height: auto; aspect-ratio: 1000 / 460; min-height: 0; padding: 0; margin: 0; background: #fbf8f4; }
  .packed-word-cloud .word-cloud__item { position: absolute; left: var(--cloud-x); top: var(--cloud-y); width: var(--cloud-w); height: var(--cloud-h); max-width: none; display: flex; justify-content: center; align-items: center; padding: 0; margin: 0; color: var(--cloud-tone); font-size: var(--cloud-font); line-height: 1.5; border: 0; background: transparent; }
  .packed-word-cloud .word-cloud__item b { font-weight: 750; overflow: visible; letter-spacing: 0; }
  .packed-word-cloud .word-cloud__item[data-cloud-emphasis="high"] { color: var(--cloud-tone); }
  .packed-word-cloud .word-cloud__item:has(input:checked) { color: var(--cloud-tone); background: transparent; box-shadow: none; text-decoration: underline; text-decoration-color: #cb986477; text-underline-offset: .17em; }
  .packed-word-cloud .cloud-word-count { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  body[data-report-format="modules"] .packed-word-cloud .word-cloud__item { color: #62584f; }
  body[data-report-format="modules"] .packed-word-cloud .word-cloud__item:has(input:checked) { color: #62584f; text-decoration: none; }
  body[data-report-format="modules"] .packed-word-cloud .word-cloud__item:has(input:focus-visible) { outline: 2px solid #b57b29; outline-offset: 3px; border-radius: 4px; }
  .cloud-ranking-disclosure { margin: 16px 0; border: 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 10px 0; }
  .cloud-ranking-disclosure > summary { cursor: pointer; font-size: 12px; color: var(--accent-strong); }
  .cloud-ranking-disclosure .cloud-rankings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 24px; padding: 12px 0; border: 0; }
  .cloud-ranking-disclosure .cloud-rankings h4, .cloud-ranking-disclosure .cloud-rankings > p { grid-column: 1 / -1; }
  @media screen and (max-width: 900px) { body[data-report-format="modules"] .reference-ranking-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
  @media screen and (max-width: 600px) {
    .reference-needs-grid { grid-template-columns: minmax(0, 1fr); }
    body[data-report-format="modules"] .reference-ranking-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .material-insight-words.word-cloud.packed-word-cloud { aspect-ratio: 400 / 540; min-height: 0; }
    .packed-word-cloud .word-cloud__item { left: var(--cloud-mobile-x); top: var(--cloud-mobile-y); width: var(--cloud-mobile-w); height: var(--cloud-mobile-h); font-size: var(--cloud-mobile-font); }
    .reference-material-counts > div { padding: 10px 12px; }
    .reference-material-counts { gap: 8px; }
  }
  body[data-report-format="modules"] .reference-voc-group { --voc-color: #8556c3; --voc-tint: #eee5fc; padding: 24px; border: 0; border-radius: 14px; background: #faf8f8; }
  body[data-report-format="modules"] .reference-voc-group[data-voc-kind="购买顾虑"] { --voc-color: #5288bd; --voc-tint: #e5f0ff; }
  body[data-report-format="modules"] .reference-voc-group[data-voc-kind="高频问题"] { --voc-color: #329972; --voc-tint: #def5e9; }
  body[data-report-format="modules"] .reference-voc-group[data-voc-kind="正向反馈"] { --voc-color: #cc5893; --voc-tint: #fce3ef; }
  body[data-report-format="modules"] .reference-voc-group > header { align-items: center; padding: 0; margin-bottom: 24px; border: 0; }
  body[data-report-format="modules"] .reference-voc-group > header h3 { margin: 0; padding: 5px 12px; border-radius: 20px; color: var(--voc-color); background: var(--voc-tint); font-size: 15px; font-weight: 750; line-height: 1.6; }
  body[data-report-format="modules"] .reference-voc-group > header > span { font-size: 11px; font-weight: 400; color: #817871; }
  body[data-report-format="modules"] .reference-voc-group .voc-item { grid-template-columns: 19px minmax(0, 1fr); align-items: baseline; gap: 10px; padding: 0; margin-bottom: 24px; border: 0; }
  body[data-report-format="modules"] .reference-voc-group .voc-item:last-child { margin-bottom: 0; }
  .reference-voc-group .voc-rank { width: 18px; height: 18px; border-radius: 50%; color: #fff; background: var(--voc-color); text-align: center; font: 750 12px/18px var(--font-body); }
  .reference-voc-group .voc-item__main > strong { font-size: 16px; font-weight: 750; line-height: 1.6; }
  .reference-voc-group .voc-metrics { gap: 8px; margin-top: 3px; }
  body[data-report-format="modules"] .reference-voc-group .voc-metrics span { padding: 0; color: #817871; background: transparent; border: 0; border-radius: 0; font: 400 11px/1.7 var(--font-body); }
  body[data-report-format="modules"] .reference-voc-group .voc-item blockquote { margin: 6px 0 0; padding: 0; border: 0; border-radius: 0; background: transparent; color: #635950; font-size: 14px; line-height: 1.8; }
  .reference-voc-group .voc-source { margin-top: 4px; color: #817871; font-size: 11px; line-height: 1.7; }
  body[data-report-format="modules"] h1, body[data-report-format="modules"] h2, body[data-report-format="modules"] h3, body[data-report-format="modules"] h4 { font-family: var(--font-display); }
  .reference-summary-card > strong { font-weight: 750; }
  body[data-report-format="modules"] .reference-module-intro > header > p { max-width: 80ch; font-size: 14px; line-height: 1.85; }
  body[data-report-format="modules"] .reference-intro-body h4 { font-size: 15px; line-height: 1.6; }
  body[data-report-format="modules"] .reference-intro-body p, .reference-intro-actions ol { font-size: 14px; }
  body[data-report-format="modules"] .profile-platform-index { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin: 18px 0; padding: 14px 18px; border: 1px solid #cfe8da; border-radius: 10px; background: #eaf7ef; }
  body[data-report-format="modules"] .profile-platform-index > strong { font-size: 14px; font-weight: 750; }
  body[data-report-format="modules"] .profile-platform-index > div { display: flex; flex-wrap: wrap; gap: 8px; }
  body[data-report-format="modules"] .profile-platform-index span { padding: 3px 6px; color: #286d4d; background: transparent; font-size: 12px; font-weight: 700; }
  body[data-report-format="modules"] .profile-panel__head { min-height: 92px; }
  body[data-report-format="modules"] .profile-kpi strong { color: var(--accent-strong); font-weight: 750; }
  body[data-report-format="modules"] .reference-audience-strategies > h3 { margin: 0 0 18px; color: var(--accent-strong); font-size: 21px; font-weight: 750; }
  body[data-report-format="modules"] .method-playbook > header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 7px; padding-bottom: 16px; }
  body[data-report-format="modules"] .method-playbook > header span, body[data-report-format="modules"] .method-playbook > header strong { color: #5887b8; font-size: 20px; font-weight: 750; line-height: 1.5; letter-spacing: 0; }
  body[data-report-format="modules"] .material-card > .reference-material-tags { margin: 0 0 12px; }
  body[data-report-format="modules"] .audience-route .audience-order { display: inline-flex; align-items: center; gap: 8px; padding: 0; color: var(--route-color); background: transparent; font-size: 12px; }
  .audience-route .audience-order::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  body[data-report-format="modules"] .audience-route .route-arrow { color: var(--route-color); opacity: .65; }
  body[data-report-format="modules"] .audience-route__advice { display: flex; align-items: baseline; gap: 8px; margin-top: 12px; padding: 13px 16px; border-radius: 9px; background: rgb(255 255 255 / .7); line-height: 1.8; }
  .audience-route__advice > span { flex-shrink: 0; color: var(--route-color); font-size: 13px; font-weight: 750; }
  .audience-route__advice > strong { color: #38312e; font-size: 15px; font-weight: 750; }
  body[data-report-format="modules"] .audience-route .audience-evidence { display: block; max-width: none; margin: 10px 0 0; color: #81766f; font-size: 11px; line-height: 1.8; }
  body[data-report-format="modules"] .audience-evidence > span { display: inline; padding: 0; margin-right: 6px; color: inherit; background: transparent; font-size: inherit; font-weight: 500; }
  body[data-report-format="modules"] .evidence-disclosure { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
  body[data-report-format="modules"] .evidence-disclosure > summary { display: flex; align-items: center; justify-content: flex-start; gap: 10px; min-height: 54px; padding: 14px 18px; background: #fff; color: #50483e; font-size: 14px; font-weight: 700; }
  body[data-report-format="modules"] .evidence-disclosure > summary::before { content: '›'; font: 500 20px/1 var(--font-body); color: var(--accent-strong); }
  body[data-report-format="modules"] .evidence-disclosure[open] > summary::before { transform: rotate(90deg); }
  body[data-report-format="modules"] .evidence-disclosure > summary small { margin-left: auto; color: #81766f; font-size: 11px; font-weight: 400; }
  .reference-closing { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr); gap: 28px; margin: 32px 0; padding: 32px; border: 1px solid #efd0b6; border-radius: 18px; background: linear-gradient(110deg, #fff1e2, #fff9f2); }
  .reference-closing > div > span { color: #be7552; font-size: 13px; font-weight: 750; }
  .reference-closing h2 { margin: 12px 0 16px; color: #493426; font-size: 30px; font-weight: 800; line-height: 1.5; }
  .reference-closing p { margin: 0; color: #826d5c; font-size: 14px; line-height: 1.9; }
  .reference-closing ol { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
  .reference-closing li { display: flex; flex-direction: column; gap: 10px; padding: 16px; border: 1px solid #f0d8c4; border-radius: 12px; background: #fff; }
  .reference-closing li > span { color: #bd704a; font: 750 12px/1.5 var(--font-data); }
  .reference-closing li > strong { color: #45382d; font-size: 16px; font-weight: 750; line-height: 1.6; }
  .reference-closing li > p { color: #81746b; font-size: 12px; line-height: 1.8; }
  .reference-closing > .reference-closing-note { grid-column: 1 / -1; margin: 0; color: #887768; font-size: 12px; }
  @media screen and (max-width: 900px) {
    body[data-report-format="modules"] .fact-item.reference-fact { grid-template-columns: minmax(0, 1fr); gap: 8px; }
    body[data-report-format="modules"] .profile-panel__head { min-height: 0; }
    .reference-closing { grid-template-columns: minmax(0, 1fr); }
  }
  @media screen and (max-width: 600px) {
    body[data-report-format="modules"] .reference-selling-groups, body[data-report-format="modules"] .ordinal-visual:has(.reference-ranking-grid) { padding: 16px; }
    .reference-need-benefit { display: block; margin-top: 4px; }
    .reference-need-benefit > span { display: none; }
    body[data-report-format="modules"] .reference-gender-grid h4 { min-height: 0; }
    body[data-report-format="modules"] .evidence-disclosure > summary { flex-wrap: wrap; }
    body[data-report-format="modules"] .evidence-disclosure > summary small { margin: 0 0 0 18px; flex-basis: 100%; }
    body[data-report-format="modules"] .audience-route__advice { display: block; padding: 12px; }
    .audience-route__advice > span { display: block; margin-bottom: 5px; }
    .reference-closing { padding: 22px 18px; gap: 18px; }
    .reference-closing h2 { font-size: 26px; }
    .reference-closing ol { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media print {
    .reference-closing { break-inside: avoid; padding: 20px; box-shadow: none; }
    body[data-report-format="modules"] .profile-board { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    body[data-report-format="modules"] .profile-panel { padding: 12px; }
    body[data-report-format="modules"] .profile-panel__head { min-height: 0; }
    body[data-report-format="modules"] .reference-needs-grid { break-inside: avoid; }
    body[data-report-format="modules"] .voc-board { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    body[data-report-format="modules"] .reference-voc-group { break-inside: avoid; }
  }
  @media screen {
    body[data-report-format="modules"] .print-module-copy { display: none; }
  }
  @media screen and (max-width: 900px) {
    body[data-report-format="modules"] .shell { width: calc(100% - 32px); margin-top: 16px; }
    .reference-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .reference-intro-body { grid-template-columns: minmax(0, 1fr); }
    .reference-intro-deliverables { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media screen and (max-width: 600px) {
    body[data-report-format="modules"] .shell { width: calc(100% - 20px); }
    body[data-report-format="modules"] .reference-cover { padding: 22px 16px; }
    .reference-cover h1 { font-size: 26px; }
    .reference-subtitle { font-size: 13px; }
    .reference-summary { padding: 16px; }
    .reference-summary-grid, .reference-gender-grid, .reference-intro-deliverables { grid-template-columns: minmax(0, 1fr); }
    .reference-audience-strategies > article { grid-template-columns: minmax(0, 1fr); gap: 12px; }
    body[data-report-format="modules"] .report-section { padding: 0 16px 24px; margin: 20px 0; }
    body[data-report-format="modules"] .report-section > h2 { margin: 0 -16px 20px; padding: 16px; font-size: 20px; }
    .reference-module-intro > header, .reference-intro-body { padding: 18px; }
    body[data-report-format="modules"] .reference-module-intro > header > h3 { font-size: 20px; }
    .reference-gender-overview { padding: 18px; }
    body[data-report-format="modules"] .fact-item, body[data-report-format="modules"] .material-card, body[data-report-format="modules"] .voc-group, body[data-report-format="modules"] .audience-route { padding: 16px; }
    body[data-report-format="modules"] .material-insight-cloud.keyword-panel { padding: 16px; }
  }
  @media print {
    body[data-report-format="modules"] { font-size: 10.5pt; background: #fff; }
    body[data-report-format="modules"] .shell { width: 100%; margin: 0; }
    body[data-report-format="modules"] .reference-cover { padding: 20px; break-after: page; }
    .reference-summary-card { break-inside: avoid; }
    .reference-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    body[data-report-format="modules"] .report-section { padding: 0 0 20px; margin-top: 0; border: 0; box-shadow: none; break-before: page; }
    body[data-report-format="modules"] .report-section > h2 { margin: 0 0 20px; break-after: avoid; }
    body[data-report-format="modules"] .reference-module-intro { break-inside: avoid; box-shadow: none; }
    .reference-intro-body { gap: 16px; padding: 16px; }
    .reference-gender-overview { break-inside: avoid; }
    .reference-audience-strategies > article { break-inside: avoid; }
    .reference-gender-ring { width: 105px; height: 105px; }
    .reference-gender-ring > div { width: 79px; height: 79px; }
    .reference-gender-ring strong { font-size: 19px; }
    body[data-report-format="modules"] .fact-item, body[data-report-format="modules"] .material-card, body[data-report-format="modules"] .selling-item, body[data-report-format="modules"] .audience-route { break-inside: avoid; }
    body[data-report-format="modules"] .fact-item, body[data-report-format="modules"] .selling-item { padding: 16px; }
  }
  `
}
