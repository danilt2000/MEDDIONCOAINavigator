/// HL7v2 ORU^R01 -> SDA3 container, forwarded to the SDA3 -> FHIR process with PatientResourceId = PID-3 (the MEDDI id,
/// which is also the FHIR id of the seeded Patient, e.g. Patient/ONC-001).
Class MEDDI.LabHL7.Process Extends Ens.BusinessProcess [ ClassType = persistent ]
{

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

Property TargetConfigName As Ens.DataType.ConfigName [ InitialExpression = "MEDDI.SDA3ToFHIR" ];

Method OnRequest(pRequest As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
	set tSC = ##class(HS.Gateway.HL7.HL7ToSDA3).GetSDA(pRequest, .sda)
	quit:$$$ISERR(tSC) tSC
	set message = ##class(HS.Message.XMLMessage).%New()
	do message.ContentStream.CopyFrom(sda)
	do message.AdditionalInfo.SetAt(pRequest.FindSegment("PID").GetValueAt("3(1).1"), "PatientResourceId")
	quit ..SendRequestSync(..TargetConfigName, message, .pResponse)
}

}
