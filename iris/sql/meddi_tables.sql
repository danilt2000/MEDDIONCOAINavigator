-- MEDDI engine tables (spec §7), namespace FHIRSERVER, schema MEDDI.
-- LEVEL is a reserved word in IRIS SQL, so the spec's "Level" columns are named TriageLevel.
-- Loaded by: python -m app.fhir.sql_tables

CREATE TABLE IF NOT EXISTS MEDDI.Triage_Rule (
    RuleId VARCHAR(30), MinLevel INT, Area VARCHAR(40), Expr VARCHAR(500),
    PatientHint VARCHAR(300), Source VARCHAR(120), Active BIT);

CREATE TABLE IF NOT EXISTS MEDDI.Drug_Class (Drug VARCHAR(80), Class VARCHAR(40));

CREATE TABLE IF NOT EXISTS MEDDI.Triage_Result (
    CheckinId VARCHAR(40), PatientId VARCHAR(12), AsOf TIMESTAMP, TriageLevel INT, Step VARCHAR(20),
    Contact VARCHAR(160), NotifyTeam BIT, RuleIds VARCHAR(300), Confidence VARCHAR(10), EngineVersion VARCHAR(40),
    Source VARCHAR(10));

CREATE TABLE IF NOT EXISTS MEDDI.Eval_Expected (
    CheckinId VARCHAR(20), Dataset VARCHAR(12), TriageLevel INT, Step VARCHAR(20), NotifyTeam BIT, Contact VARCHAR(160));

CREATE TABLE IF NOT EXISTS MEDDI.Eval_Run (
    RunId VARCHAR(40), CheckinId VARCHAR(20), Expected INT, Predicted INT, StepOk BIT, ContactOk BIT, NotifyOk BIT);

-- SQL projections of the FHIR repository (JsonAdvSQL resource table HSFHIR_X0001_R.Rsrc) for trends and dashboards.
-- Times are the FHIR strings with offset (e.g. 2026-09-09T21:52:00+02:00), so they sort chronologically within a patient.

CREATE OR REPLACE VIEW MEDDI.FHIR_Observation AS
SELECT r.ResourceId, j.PatientRef, j.EffectiveAt, j.Category, j.Loinc, j.Display, j.NumValue, j.IntValue, j.Unit,
       j.Systolic, j.Diastolic, j.Device, j.Interpretation
FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (
    PatientRef VARCHAR(40) PATH '$.subject.reference',
    EffectiveAt VARCHAR(40) PATH '$.effectiveDateTime',
    Category VARCHAR(20) PATH '$.category[0].coding[0].code',
    Loinc VARCHAR(20) PATH '$.code.coding[0].code',
    Display VARCHAR(200) PATH '$.code.text',
    NumValue NUMERIC(12,3) PATH '$.valueQuantity.value',
    IntValue INT PATH '$.valueInteger',
    Unit VARCHAR(20) PATH '$.valueQuantity.unit',
    Systolic INT PATH '$.component[0].valueQuantity.value',
    Diastolic INT PATH '$.component[1].valueQuantity.value',
    Device VARCHAR(40) PATH '$.device.display',
    Interpretation VARCHAR(4) PATH '$.interpretation[0].coding[0].code')) j
WHERE r.ResourceType = 'Observation' AND r.Deleted = 0;

CREATE OR REPLACE VIEW MEDDI.FHIR_Risk AS
SELECT r.ResourceId, j.PatientRef, j.CheckinId, j.OccurredAt, j.TriageLevel, j.Step, j.EngineVersion, j.Rationale
FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (
    PatientRef VARCHAR(40) PATH '$.subject.reference',
    CheckinId VARCHAR(40) PATH '$.identifier[0].value',
    OccurredAt VARCHAR(40) PATH '$.occurrenceDateTime',
    TriageLevel INT PATH '$.prediction[0].qualitativeRisk.coding[0].code',
    Step VARCHAR(20) PATH '$.prediction[0].outcome.coding[0].code',
    EngineVersion VARCHAR(40) PATH '$.method.text',
    Rationale VARCHAR(4000) PATH '$.note[0].text')) j
WHERE r.ResourceType = 'RiskAssessment' AND r.Deleted = 0;

CREATE OR REPLACE VIEW MEDDI.FHIR_Task AS
SELECT r.ResourceId, j.PatientRef, j.Code, j.Status, j.Priority, j.Description, j.OwnerName, j.AuthoredOn, j.SlaEnd
FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (
    PatientRef VARCHAR(40) PATH '$.for.reference',
    Code VARCHAR(30) PATH '$.code.coding[0].code',
    Status VARCHAR(20) PATH '$.status',
    Priority VARCHAR(10) PATH '$.priority',
    Description VARCHAR(1000) PATH '$.description',
    OwnerName VARCHAR(160) PATH '$.owner.display',
    AuthoredOn VARCHAR(40) PATH '$.authoredOn',
    SlaEnd VARCHAR(40) PATH '$.restriction.period.end')) j
WHERE r.ResourceType = 'Task' AND r.Deleted = 0;
