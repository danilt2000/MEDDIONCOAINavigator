/// Standard SDA3 -> FHIR transform, then aligned with the seeded data (app/fhir) and made idempotent:
/// - Patient: references point to Patient/{PID-3}; if that Patient already exists its entry is dropped (never overwritten),
///   otherwise it is created under that id with identifier urn:meddi:patient|{PID-3}, which the seed later overwrites in place.
/// - lab Observations get identifier urn:meddi:lab|{odber_id}-{kod}, the same as the seeded ones;
/// - every POST becomes a conditional create (ifNoneExist on its identifier), so a lab already seeded or a file dropped
///   twice adds nothing.
Class MEDDI.LabHL7.Transform Extends HS.FHIR.DTL.Util.API.Transform.SDA3ToFHIR
{

Parameter ENDPOINT = "/fhir/r4";

/// LOINC -> MEDDI lab kod as used in the seeded identifiers ("_" folded to "-").
Parameter MEDDICODES = "6690-2:leu,751-8:neu,718-7:hb,777-3:plt,14682-9:kreat,2951-2:na,2823-3:k,1742-6:alt,14631-6:bili,1988-5:crp,3016-3:tsh,14920-3:ft4,2601-3:mg,6301-6:inr,1751-7:alb,2857-1:psa,14913-8:testo,14749-6:glu,20454-5:moc-bilk,33762-6:ntprobnp";

ClassMethod TransformStream(stream As %Stream.Object, SDAClassname As %String, fhirVersion As %String, patientId As %String = "", encounterId As %String = "", createPlaceholderExtensions As %Boolean = 1) As HS.FHIR.DTL.Util.API.Transform.SDA3ToFHIR
{
	set transformer = ##super(stream, SDAClassname, fhirVersion, patientId, encounterId, createPlaceholderExtensions)
	do ..AlignWithSeed(transformer.bundle, patientId)
	return transformer
}

ClassMethod AlignWithSeed(bundle As %DynamicObject, patientId As %String)
{
	set patientExists = ..PatientExists(patientId), orderId = ""
	for index = bundle.entry.%Size() - 1:-1:0 {
		set resource = bundle.entry.%Get(index).resource
		if resource.resourceType = "DiagnosticReport" set orderId = resource.identifier.%Get(0).value
		if (resource.resourceType = "Patient") && patientExists do bundle.entry.%Remove(index)
	}
	set iterator = bundle.entry.%GetIterator()
	while iterator.%GetNext(, .entry) {
		set resource = entry.resource, key = ""
		if resource.resourceType = "Patient" {
			set resource.identifier.%Get(0).system = "urn:meddi:patient"
		} elseif resource.resourceType = "Observation" {
			set value = orderId_"-"_..MeddiCode(resource.code.coding.%Get(0).code)
			set resource.identifier = [{"system": "urn:meddi:lab", "value": (value)}]
			set key = "urn:meddi:lab|"_value
		} elseif $isobject(resource.identifier) {
			set key = resource.identifier.%Get(0).value
		}
		if (key '= "") && (entry.request.method = "POST") set entry.request.ifNoneExist = "identifier="_key
	}
}

ClassMethod MeddiCode(loinc As %String) As %String
{
	set pairs = ","_..#MEDDICODES_","
	quit:pairs'[(","_loinc_":") loinc
	quit $piece($piece(pairs, ","_loinc_":", 2), ",")
}

ClassMethod PatientExists(patientId As %String) As %Boolean
{
	quit:patientId="" 0
	set exists = 1
	try {
		do ##class(HS.FHIRServer.API.InteractionsStrategy).GetStrategyForEndpoint(..#ENDPOINT).NewInteractionsInstance().Read("Patient", patientId)
	} catch {
		set exists = 0
	}
	quit exists
}

}
