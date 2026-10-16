/// Entry point for alerts from the navigator backend (Python native API):
/// iris.createIRIS(conn).classMethodValue("MEDDI.Alert.Service", "Send", json) -> 1 when queued for MEDDI.Alert.Operation.
Class MEDDI.Alert.Service Extends Ens.BusinessService
{

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

Property TargetConfigName As Ens.DataType.ConfigName [ InitialExpression = "MEDDI.Alert.Operation" ];

ClassMethod Send(json As %String) As %Boolean
{
	quit:'##class(Ens.Director).IsProductionRunning() 0
	quit:$$$ISERR(##class(Ens.Director).CreateBusinessService("MEDDI.Alert.Service", .service)) 0
	quit $$$ISOK(service.ProcessInput(##class(Ens.StringRequest).%New(json)))
}

Method OnProcessInput(pInput As Ens.StringRequest, Output pOutput As %RegisteredObject) As %Status
{
	quit ..SendRequestAsync(..TargetConfigName, pInput)
}

}
