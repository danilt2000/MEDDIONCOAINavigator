<div align="center">

<img src="apps/patient-pwa/public/favicon.svg" width="84" alt="MEDDI navigator logo">

# MEDDIONCO AI Navigator

**A safe companion for people on cancer treatment, for the days between doctor visits.**<br>
The patient learns what to do next. The care team learns who needs help first.

[![Rakathon 2026](https://img.shields.io/badge/Rakathon-2026-0E6B5C)](https://www.rakathon.cz/#rv-praha)
[![MEDDI ONCO Challenge](https://img.shields.io/badge/MEDDI%20ONCO-Challenge-B3261E)](#the-challenge)
[![InterSystems challenge](https://img.shields.io/badge/InterSystems-challenge-333695)](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/)

**[Try the patient app ↗](https://pacient.nastasiya.com/?patient=ONC-001)** ·
**[Open the clinician web ↗](https://lekar.nastasiya.com/#/fronta)** ·
[Technical documentation](docs/README.md)

<img src="docs/screenshots/hero.png" width="100%" alt="One check-in, two screens: the patient app shows a red card asking to call 155 or the on-duty doctor now; the clinician web shows the red task for Jana K. with a 15-minute countdown and a short summary">

<sub>Jana is on chemotherapy and gets a fever late in the evening. Her phone tells her to call right away;
the doctor on duty sees her at the top of the list with a 15-minute countdown and a short summary.</sub>

</div>

## Why it matters

Cancer treatment weakens the body. Between visits, patients often feel unwell and do not know whether it can wait
until tomorrow or whether they should call right now. A fever that is harmless for most people can be an emergency
ten days after chemotherapy.

Patients of the Masaryk Memorial Cancer Institute (MOÚ) already answer a short questionnaire at home in the
MEDDI Onco app. Today each answer is judged on its own. Our navigator looks at the whole picture: the answers,
the treatment, how the patient felt on earlier days and what they write in their own words.

## The challenge

Our entry for the **MEDDI ONCO Challenge** (challenge 5 of the Prague track, set by MEDDI Hub) at
[Rakathon 2026](https://www.rakathon.cz/#rv-praha), also submitted to the
[InterSystems challenge](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/).

> An AI navigator that supports an oncology patient also *between* check-ups. It keeps following the symptoms,
> recognises risky changes and recommends a safe next step. When the patient gets worse, it alerts the care team in
> time and gives the doctor a short, clear overview of how the patient's condition developed.

| The challenge asks for | What we built |
|---|---|
| Support between check-ups | A phone app with a short daily check-in and a chat, in Czech and Slovak; a relative can write for the patient |
| Keep following the symptoms | Every answer is compared with the earlier days and with the patient's usual values |
| Recognise risky changes | 49 medical rules that know the treatment: what is normal after one drug can be dangerous after another |
| Recommend a safe next step | One of four colours with one clear instruction and the right phone number |
| Alert the team in time | The right person in the care team gets a task with a countdown, day and night |
| A short overview for the doctor | A summary that can be read in 30 seconds: why now, treatment, trend, lab results |

## How it works

1. **The patient checks in.** A few questions chosen for their treatment, plus room to describe the problem in their
   own words. A relative can fill it in for them.
2. **The navigator looks at the whole situation.** Medical rules compare today's answers with the treatment and the
   previous days, and AI helps to understand what the patient wrote.
3. **Everyone gets their next step.** The patient sees one clear instruction and whom to call. If help is needed,
   the right person in the care team gets a task with a deadline and a short summary.

| | The patient sees | Who in the care team is told | How fast |
|---|---|---|---|
| 🟢 **Green** | Keep monitoring | Nobody needs to act | – |
| 🟡 **Yellow** | Contact the team | The monitoring centre | By the end of the next working day |
| 🟠 **Orange** | A video or phone consultation today | A doctor through the monitoring centre; at night the doctor on duty | Within 2 hours; at night right away |
| 🔴 **Red** | Call now: 155 or the doctor on duty | The monitoring centre; at night the doctor on duty | Within 15 minutes |

## Safe by design

- **No diagnoses, no dose changes.** The navigator never tells the patient what illness they have and never changes
  or calculates a dose of medicine.
- **AI does not decide how serious it is.** Fixed medical rules set the colour. AI only helps to read free text,
  and it can only make the colour more urgent, never less.
- **When in doubt, it escalates.** If something is unclear, the navigator asks back or chooses the safer colour.
- **A person always closes the loop.** Every yellow, orange or red ends with a nurse or a doctor.
- **Checked words.** Every message the patient reads passes a safety check first.

## Try it yourself

The demo is live and uses made-up patients only. Open the patient app on a phone (or a narrow browser window) and the
clinician web on a computer. The apps are in Czech; the patient app also speaks Slovak. The demo clock starts on a
Wednesday at 21:50, outside working hours, so urgent cases go to the doctor on duty.

| Story | Open | What to do | What happens |
|---|---|---|---|
| **Fever after chemotherapy** | [Jana K. ↗](https://pacient.nastasiya.com/?patient=ONC-001) | Tick *Zvýšená teplota a horečky* and *Únava a slabost*, then enter temperature *38,4* | 🔴 Call now; the doctor on duty gets the task with a 15-minute countdown |
| **The form and the message disagree** | [Štefan Ď. ↗](https://pacient.nastasiya.com/?patient=ONC-018) | Tick only *Únava a slabost*, then write „od vcera mam hnacku asi 6 krat, slaby som“ | 🟠 The text mentions diarrhoea six times a day, so the navigator raises the colour and asks back in Slovak |
| **A daughter writes for her mother** | [Ludmila T. ↗](https://pacient.nastasiya.com/navigator?patient=ONC-014) | Ask „Můžu mamince dát další Oramorph?“ | No extra dose without a doctor; the navigator quotes the prescription exactly and asks how many doses were given |

Then open the clinician web and see what the care team sees:

- **[Queue ↗](https://lekar.nastasiya.com/#/fronta):** the most urgent patients first, each with a countdown and a short summary.
- **[Monitoring ↗](https://lekar.nastasiya.com/#/monitoring):** alerts and check-ins over time, by treatment and by symptom.
- **[Patient detail ↗](https://lekar.nastasiya.com/#/pacienti/ONC-001):** treatment, measurements over time and everything the patient reported.
- **[Notification test ↗](https://lekar.nastasiya.com/#/test-notifikace?patient=ONC-001):** turn on notifications in the patient app (*Nastavení*), then send a real reminder to your phone; a tap opens the check-in.

## What it looks like

### Patient app

<table>
  <tr>
    <td width="33%" align="center" valign="top">
      <img src="docs/screenshots/patient-checkin-start.png" alt="The app opens on the check-in: question 1 of 5, a note that today's check-in was red, a red phone button and the AI button">
      <br><sub><b>Check-in first.</b> The app opens on today's questions; the red phone shows the warning signs, <i>AI</i> opens the chat.</sub>
    </td>
    <td width="33%" align="center" valign="top">
      <img src="docs/screenshots/patient-checkin-fever.png" alt="Check-in question about fever, marked as asked because of chemotherapy">
      <br><sub><b>Questions follow the treatment.</b> This one is asked <i>because of chemotherapy</i>.</sub>
    </td>
    <td width="33%" align="center" valign="top">
      <img src="docs/screenshots/patient-result-red.png" alt="Red result: call 155 or the on-duty doctor, do not take paracetamol, the team has been alerted">
      <br><sub><b>Red.</b> One clear step, both phone numbers, a warning not to take paracetamol, and a note that the team already knows.</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top">
      <img src="docs/screenshots/patient-acute.png" alt="Akutní potíže dialog: when to call at once, with Ambulance and 155 buttons">
      <br><sub><b>Feeling very bad?</b> The warning signs in plain words and a call button, one tap away.</sub>
    </td>
    <td align="center" valign="top">
      <img src="docs/screenshots/patient-chat-caregiver-2.png" alt="Navigator chat in caregiver mode escalates to orange: call the on-duty doctor now, no dose beyond the prescription">
      <br><sub><b>For relatives.</b> Two doses given and the pain is still 8 of 10 → orange: call the doctor on duty, no extra dose.</sub>
    </td>
    <td align="center" valign="top">
      <img src="docs/screenshots/patient-result-orange-sk.png" alt="Slovak orange result asking back about diarrhoea six times a day">
      <br><sub><b>In Slovak.</b> The form says no diarrhoea, the message says six times a day → orange and a question back.</sub>
    </td>
  </tr>
</table>

### Clinician web

<img src="docs/screenshots/doctor-queue.png" width="100%" alt="Queue: red task for Jana K. on top with the countdown, orange and yellow tasks below, the task detail with actions and the 30-second summary">

<sub><b>Queue.</b> The most urgent patient is on top with a countdown; a red banner stays on every page until someone takes the task.</sub>

<img src="docs/screenshots/doctor-patient.png" width="100%" alt="Patient detail of Hana D. on trastuzumab: cardiotoxic tag, weight rising from 83.4 to 85.8 kg, blood pressure chart and a timeline with check-ins and a nurse note">

<sub><b>Patient detail.</b> Hana D. takes a drug that can strain the heart; her weight rose by 2.4 kg in 6 days, so the team sees it at once.</sub>

<img src="docs/screenshots/doctor-monitoring.png" width="100%" alt="Monitoring: alert and check-in charts over one range strip, alerts by treatment">

<sub><b>Monitoring.</b> How many alerts and check-ins came in, day by day; click a day, a treatment or a symptom to see the patients.</sub>

<details>
<summary><b>More screens</b></summary>

<img src="docs/screenshots/doctor-regimen.png" width="100%" alt="All alerts on sunitinib with the reason and what the team did">

<sub><b>By treatment.</b> Every alert for patients on one drug: why it came and what the team did.</sub>

<img src="docs/screenshots/doctor-rules.png" width="100%" alt="Rules page: routing by working hours, deadlines and the rule list">

<sub><b>Rules.</b> Who is told and how fast, in and out of working hours; the rules set the colour, AI never does.</sub>

</details>

## Results

We replayed 1,320 made-up check-ins from the challenge data, day by day, and compared the navigator with the answers
expected by the organisers.

| | Result | Goal of the challenge |
|---|---|---|
| 🔴 Emergencies caught | **100 %** | 100 % |
| Patients rated less urgent than they were | **0 %** | at most 3 % |
| Harmless check-ins sent to the team anyway | **about 3 %** | at most 15 % |
| Colour exactly as expected | **98 %** | at least 85 % |

The full numbers are in the [technical documentation](docs/README.md#metrics).

## Under the hood

Health data is stored in **InterSystems IRIS for Health** in the healthcare standard **FHIR**, so the navigator can
connect to existing hospital systems, and alerts go out through a proposed interface for MEDDI. How it is built, how to run it and
every rule: [technical documentation](docs/README.md).

> [!NOTE]
> This is a hackathon prototype with made-up data. It is not a medical device. If you feel unwell, call your doctor
> or 155.
