<div align="center">

<img src="apps/patient-pwa/public/favicon.svg" width="84" alt="MEDDI navigator logo">

# MEDDIONCO AI Navigator

**A safe companion for people on cancer treatment, for the days between doctor visits.**<br>
The patient learns what to do next. The care team learns who needs help first.

[![Rakathon 2026](https://img.shields.io/badge/Rakathon-2026-0E6B5C)](https://www.rakathon.cz/#rv-praha)
[![MEDDI ONCO Challenge](https://img.shields.io/badge/MEDDI%20ONCO-Challenge-B3261E)](docs/README.md#the-challenge)
[![InterSystems challenge](https://img.shields.io/badge/InterSystems-challenge-333695)](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/)

**[Try the patient app ↗](https://pacient.nastasiya.com/?patient=ONC-001)** ·
**[Open the clinician web ↗](https://lekar.nastasiya.com/#/fronta)** ·
[Technical documentation](docs/README.md)

<img src="docs/screenshots/hero.png" width="100%" alt="One check-in, two screens: the patient app shows a red card asking to call 155 or the on-duty doctor now; the clinician web shows the red task for Jana K. with a 15-minute countdown and a short summary">

<sub>Jana is on chemotherapy and gets a fever late in the evening. Her phone tells her to call right away;
the doctor on duty sees her at the top of the list with a 15-minute countdown and a short summary.</sub>

</div>

## See it in action

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <img src="docs/screenshots/demo-checkin.gif" width="300" alt="Recording: Jana fills in the check-in on her phone, ticks fever and fatigue, enters 38.4 °C and a short message, and gets a red card asking her to call 155 or the on-duty doctor now">
      <br><sub><b>Check-in.</b> Jana has a fever ten days after chemotherapy. A few taps later her phone says: call now, and the team already knows.</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <img src="docs/screenshots/demo-chat.gif" width="300" alt="Recording: a daughter asks the navigator chat whether she can give her mother another dose of Oramorph; the answer is yellow, then orange after she adds that two doses did not help">
      <br><sub><b>Chat for relatives.</b> A daughter asks about another dose of morphine for her mother. No extra dose without a doctor; when the pain stays at 8, it turns orange.</sub>
    </td>
  </tr>
</table>

<img src="docs/screenshots/demo-clinician.gif" width="100%" alt="Recording: the clinician queue with Jana's red task on top and a countdown, her 30-second summary, her patient detail with charts and the monitoring page">

<sub><b>The care team.</b> Jana's red task is on top with a countdown. One click shows the 30-second summary, her history and the monitoring of all patients.</sub>

## Install it like an app

<img src="docs/screenshots/install.png" width="100%" alt="The MEDDI icon on a home screen, the patient app full screen on a tablet and on a phone">

The patient app works on **phones and tablets** and can be added to the home screen. It then has its own icon
and opens full screen like any other app, with no app store needed.

| iPhone and iPad | Android | Computer |
|---|---|---|
| Open [pacient.nastasiya.com](https://pacient.nastasiya.com/) in **Safari**, tap **Share**, then **Add to Home Screen** | Open the link in **Chrome**, tap the menu **⋮**, then **Install app** or **Add to Home screen** | In **Chrome** or **Edge**, click the install icon in the address bar |

On a phone the app is one clear column; on a tablet it fills the whole screen. The clinician web is made for
computers and also opens on tablets and phones.

## Reminders on the phone

<img src="docs/screenshots/notifications.png" width="100%" alt="Left: the notification rules in the clinician web. Right: a locked phone showing two MEDDI notifications, a check-in reminder and a message from the team">

The care team decides when patients get a reminder. The patient sees it even on a locked phone, and a tap opens the
right screen.

- **Daily reminder** at a set time for everyone who has not filled in today's check-in.
- **Missed check-in** after a few days without one; a day earlier for high-risk patients.
- **Message from the team** right after the team calls, holds a video consultation or closes the task.
- **Follow-up question** when the navigator needs one more answer.

The texts never contain health data, because they show on the lock screen. The patient turns reminders on in the app
under *Nastavení* → *Zapnout upozornění*; on iPhone and iPad this works in the app added to the home screen
(iOS 16.4 or newer). The team sets the rules and can send a test reminder in
[Notifikace ↗](https://lekar.nastasiya.com/#/notifikace).

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

## InterSystems IRIS for Health

<img src="docs/screenshots/demo-iris.gif" width="100%" alt="Recording: the IRIS tab in the clinician web with the FHIRSERVER namespace, almost 7,000 FHIR resources and the running production, a SQL query over FHIR data, a FHIR Task resource and the production trace of an alert">

<sub><b>Live from the demo server.</b> The storage overview, a SQL query that reads Hana's weight straight from FHIR,
a triage task stored as a FHIR resource, and the same alert travelling through the IRIS production toward MEDDI.</sub>

<img src="docs/screenshots/demo-iris-portal.gif" width="100%" alt="The IRIS Management Portal: home with MEDDI.Production running, the production configuration with the alert operation settings, the message trace of an alert and a SQL query over FHIR observations">

<sub><b>The same in the IRIS Management Portal.</b> MEDDI.Production is running; the alert operation posts to the
MEDDI endpoint; the message trace of one alert; and a SQL query over the FHIR observations.</sub>

Everything the navigator works with is stored in **InterSystems IRIS for Health** in the healthcare standard
**FHIR**: patients, check-ins, triage results, tasks and alerts. Trends are read with SQL straight over the FHIR data,
the chat looks up guidance with IRIS Vector Search, and every alert also goes through an IRIS production toward MEDDI.
That is what lets the navigator connect to existing hospital systems.

**A check-in on its way through IRIS:**

```mermaid
stateDiagram-v2
    state "Check-in received" as Received
    state "Triage done, the patient gets the answer at once" as Triage
    state "Stored in IRIS (FHIR repository)" as Stored
    state level <<choice>>
    state "Alert via the IRIS production (Alert.Service → Operation)" as Alert
    state "MEDDI got the alert, task in the clinician queue" as Meddi
    [*] --> Received
    Received --> Triage
    Triage --> Stored
    Stored --> level
    level --> Alert : level ≥ 2
    level --> [*] : level 1
    Alert --> Meddi
    Meddi --> [*]
```

**A chat message and the AI agent.** The level is always set by rules. The AI agent only writes the words, and it can
raise the level but never lower it.

```mermaid
stateDiagram-v2
    state "Message received (patient or caregiver)" as Message
    state "Rules triage, level card at once, no AI" as Rules
    state "IRIS alert to the MEDDI queue" as Alert
    state "Guidance search (IRIS Vector Search)" as Search
    state "AI agent drafts the reply (LLM + read-only tools)" as Agent
    state "Safety check of level, medicines and contacts" as Check
    state "Reply sent, saved to IRIS FHIR" as Reply
    [*] --> Message
    Message --> Rules
    Rules --> Alert : level ≥ 2
    Alert --> [*]
    Rules --> Search
    Search --> Agent
    Agent --> Check
    Check --> Agent : rejected, retry
    Check --> Reply : ok
    Reply --> [*]
    note right of Agent
        Tools: patient context, recent check-ins, trends,
        IRIS Vector Search, contact by hour, follow-up question,
        escalate (can only raise the level)
    end note
```

See it live, no login needed: [overview ↗](https://lekar.nastasiya.com/#/iris) ·
[SQL ↗](https://lekar.nastasiya.com/#/iris/sql) · [FHIR resources ↗](https://lekar.nastasiya.com/#/iris/fhir) ·
[production traces ↗](https://lekar.nastasiya.com/#/iris/produkce) · [FHIR API ↗](https://lekar.nastasiya.com/fhir/r4/metadata).
How it is built, how to run it and every rule: [technical documentation](docs/README.md).

> [!NOTE]
> This is a hackathon prototype with made-up data. It is not a medical device. If you feel unwell, call your doctor
> or 155.
