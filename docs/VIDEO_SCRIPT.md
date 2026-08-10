# DataCapture — "How to use it" tutorial video script

**Format:** screen-recording with voiceover · **Target length:** ~9 minutes
**Audience:** clinicians / researchers new to the tool (no stats or IT background assumed)
**Demo scenario:** a small Infectious Diseases registry (so the examples feel real)

Each scene gives you **[SCREEN / ACTION]** — what to do and record — and **NARRATION** —
the words to say. Timings are approximate. Read the narration at a relaxed pace.

---

## Before you record (2-minute checklist)

- Launch DataCapture once and log in, so you're past the first-run screen (or, if you want
  to *show* the first-run, start from a fresh copy — see Scene 2).
- Set the theme to **Light** (top-right toggle) for the clearest recording; switch to
  **Glass** for a few seconds near the end if you want to show it off.
- Have a demo project half-built, OR build it live — the script below builds it live.
- **Use fake patient data only.** Never record real names, MRNs, or identifiable data.
- Set your browser zoom to ~110% and hide your bookmarks bar so text is big and clean.
- Recording tools that work well: OBS Studio (free), Xbox Game Bar (Win+G), or Loom.

---

## Scene 1 — Cold open / title (0:00–0:15)

**[SCREEN]** DataCapture dashboard on screen, or a title card that says
"DataCapture — offline research data capture."

**NARRATION:**
"This is DataCapture — a private, offline app for collecting research data on your own
computer. Think of it as a simple, self-hosted REDCap. In the next few minutes I'll show
you how to build a form, enter data, and get a publication-ready results table — all
without the internet or any subscription."

---

## Scene 2 — Launch & log in (0:15–1:05)

**[SCREEN / ACTION]** Double-click the **DataCapture** icon. The browser opens at
`localhost:8710`. (If this is a brand-new install, the first screen asks you to create an
administrator account — show typing a username, display name, and password, then continue.)
Then show the **Log in** screen and log in.

**NARRATION:**
"To start it, I just double-click the DataCapture icon. It opens in my normal web browser
at localhost — that 'localhost' address means it's running only on this computer; nothing
is being sent anywhere. The very first time, it asks you to create an administrator
account — that's you. After that, you just log in like any website, except the website is
your own machine."

---

## Scene 3 — Create a project (1:05–2:10)

**[SCREEN / ACTION]** Click **My Projects → New project** (or the New project button).
Fill in:
- **Title:** "SBO Registry"
- **Purpose:** Research (hover the explanation briefly)
- **Specialty / Department:** start typing "Infec…" and pick **Infectious Diseases**
- **Record label:** "Patient ID"
- Leave *Longitudinal* unchecked for now.
Click **Create project**.

**NARRATION:**
"A 'project' is one study or registry. I'll make an infectious-diseases registry. I give it
a title, and I pick a Purpose — DataCapture explains each one right underneath, so you know
whether you're doing research, an audit, or just practising. I'll set the Specialty to
Infectious Diseases — that's pulled from the CMC department list, and it also tailors the
suggestions I'll see in a moment. 'Record label' is what one row represents — here, one
Patient. Create — and the project's ready."

**[ON-SCREEN CAPTION]** "One project = one study or registry"

---

## Scene 4 — Design the form (2:10–3:55)

**[SCREEN / ACTION]** From the sidebar open **Form Designer**.
1. In **Instrument name**, click the box — show the dropdown of clinical sections — pick
   **Demographics**, click *Create instrument*. Add a second one: **Microbiology**.
2. Open **Demographics**. Add fields using the **Field label** dropdown:
   - "Age" → field type **Integer**
   - "Sex" → field type **Radio**, choices `1, Male | 2, Female`
   - "Diabetes" → field type **Yes/No**
3. Open **Microbiology**. Add:
   - "CRP (mg/L)" → **Number**
   - "Organism" → **Dropdown**, choices `1, Bacterial | 2, Fungal | 3, Mixed`
   - "Outcome" → **Radio**, choices `1, Cured | 2, Not cured`
   Briefly point out **Required** and **Branching logic** options, then move on.

**NARRATION:**
"Now I build the form. Each 'instrument' is one page of the form — like Demographics or
Microbiology. When I click into the name box, DataCapture suggests common sections, so I'm
not starting from a blank page. Inside an instrument I add fields — one per question. The
label box suggests common data points too. For each field I pick a type: a number, a
yes/no, or a dropdown with coded options like 1 for Bacterial, 2 for Fungal. You can mark a
field 'Required', or add branching logic so a question only appears when it's relevant — but
you can keep it simple to start. That's the whole form, built in a couple of minutes."

**[ON-SCREEN CAPTION]** "Instruments = pages · Fields = questions"

---

## Scene 5 — Enter data (3:55–5:00)

**[SCREEN / ACTION]** Sidebar → **Records → Add record** (Patient ID `1`). Open it, fill the
Demographics and Microbiology forms with plausible values, click **Save**. If you have a
file/photo field, show attaching an image. Add a second record quickly to show the
**Record Status Dashboard** filling in.

**NARRATION:**
"With the form built, I collect data. I add a record — that's one patient — and fill in the
form just like a paper CRF, then Save. If you added a file or photo field, you can attach a
scan or an image right here. The Records dashboard gives you a colour-coded grid so you can
see at a glance which forms are complete and which still need work. That's your day-to-day
screen during a study."

---

## Scene 6 — Import existing data (5:00–5:40)

**[SCREEN / ACTION]** Sidebar → **Import**. Show **Download CSV template**, mention filling
it in Excel, then show **Upload → Review → Commit** (you can pre-fill a small CSV to make
this quick).

**NARRATION:**
"Already have data in Excel? Use the Import tool. It gives you a template CSV that exactly
matches your form, you paste your data into it, upload, review what it found, and commit.
It uses the numeric codes — so a 1 or a 2 — which keeps everything consistent with the form
you built."

---

## Scene 7 — Analysis: Table One (5:40–7:05) ★ the highlight

**[SCREEN / ACTION]** Sidebar → **Analysis**. In the **Analysis** dropdown choose
**Table One (baseline characteristics)**. In **Variables** pick Age, CRP, Diabetes,
Organism. In **Grouping variable** pick **Outcome**. Click **Run analysis**. Let the
finished Table One fill the screen. Then click **Copy for Word**, switch to a Word document,
and paste — show the formatted table appearing.

**NARRATION:**
"Here's my favourite part. Open Analysis and choose 'Table One'. I pick the variables I want
to summarise, and the group I'm comparing across — here, Cured versus Not cured — and Run.
DataCapture builds the classic baseline-characteristics table: it automatically uses mean
and standard deviation for normally-distributed numbers, switches to median and
interquartile range when the data are skewed, shows counts and percentages for categories,
and runs the correct test for each row — a t-test, Mann-Whitney, or chi-square — giving you
a p-value. All of this is computed right here in Python; nothing leaves your computer. And
when I click 'Copy for Word', I can paste it straight into a manuscript as a real,
formatted table. There's a CSV button too."

**[ON-SCREEN CAPTION]** "Table One — grouped, auto-tested, paste into Word"

**NARRATION (continue):**
"The Analysis page also does descriptives, t-tests, ANOVA, correlation, regression, and
cross-tables — same idea, point and click."

---

## Scene 8 — Export to SPSS / jamovi (7:05–7:45)

**[SCREEN / ACTION]** Sidebar → **Export & Reports**. Point at **CSV (raw codes / labels)**,
**Data dictionary**, and **SPSS / jamovi (.sav)**. Click the **.sav** download.

**NARRATION:**
"If you'd rather do your full analysis in jamovi, SPSS, R, or Stata, go to Export. The
one-click SPSS file carries your variable labels, value labels, and measure types already
set up — so it opens cleanly in jamovi or SPSS with no re-coding. You also get plain CSVs
and a data dictionary."

---

## Scene 9 — Lock, share, protect (7:45–8:35)

**[SCREEN / ACTION]** Go to the project **Dashboard**. Show **Move to Production** (explain
it locks the design). Show **User Rights** (add a colleague as data-entry). Show **Audit
Trail** briefly. Point to the footer note about backing up `data/datacapture.db`.

**NARRATION:**
"When your form is final, click 'Move to Production' — that locks the design so collected
data can't be broken by accident. Under User Rights you can add colleagues and choose what
each can do — full admin, data entry only, or read only. Every change is logged in the Audit
Trail. And because your entire study lives in a single file — datacapture.db — backing up is
just copying that one file to a safe place. Do that regularly."

**[ON-SCREEN CAPTION]** "Back up data/datacapture.db regularly"

---

## Scene 10 — Stopping & outro (8:35–9:00)

**[SCREEN / ACTION]** Show **Stop DataCapture** (double-click the Stop icon), then a closing
title card.

**NARRATION:**
"When you're done, 'Stop DataCapture' shuts it down cleanly. That's the whole tool: build a
form, collect data, get a publication-ready table — private, offline, and free. Thanks for
watching."

---

## Appendix A — 3-minute quick version (if you want a short cut)

Use only these scenes, trimmed:
1. **Launch & log in** (15s) — "runs on your own computer, nothing goes online."
2. **Create project + build one instrument with 3 fields** (60s).
3. **Add one record** (30s).
4. **Table One + Copy for Word** (60s) — the wow moment.
5. **Outro** (15s) — "private, offline, free."

## Appendix B — On-screen captions (lower-third text) to add in editing

- "localhost = runs only on this computer"
- "Instruments = pages · Fields = questions"
- "Coded choices (1, 2, 3) keep data clean"
- "Table One: auto-picks the right test"
- "Copy for Word / CSV on every table"
- "Everything in one file: data/datacapture.db"

## Appendix C — Recording tips

- Record at 1920×1080. Keep the browser maximised.
- Do each click a beat slower than feels natural — it reads better on video.
- If you fluff a line, pause 2 seconds and redo the sentence; it's easy to cut later.
- Zoom in (editing) on the Table One result and the Copy-for-Word paste — those are the
  moments viewers care about most.
