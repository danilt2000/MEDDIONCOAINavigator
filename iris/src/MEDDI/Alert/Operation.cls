/// POSTs an alert (JSON in Ens.StringRequest) to the MEDDI monitoring-centre endpoint.
/// Target = adapter settings HTTPServer, HTTPPort, URL (default http://host.docker.internal:8100/mock/meddi/requests).
Class MEDDI.Alert.Operation Extends Ens.BusinessOperation
{

Parameter ADAPTER = "EnsLib.HTTP.OutboundAdapter";

Property Adapter As EnsLib.HTTP.OutboundAdapter;

Parameter INVOCATION = "Queue";

Method PostAlert(pRequest As Ens.StringRequest, Output pResponse As Ens.StringResponse) As %Status
{
	set httpRequest = ##class(%Net.HttpRequest).%New()
	set httpRequest.ContentType = "application/json; charset=utf-8"
	set httpRequest.EntityBody = ##class(%Stream.TmpCharacter).%New()
	do httpRequest.EntityBody.Write(pRequest.StringValue)
	set tSC = ..Adapter.SendFormDataArray(.httpResponse, "POST", httpRequest)
	quit:$$$ISERR(tSC) tSC
	set pResponse = ##class(Ens.StringResponse).%New(httpResponse.StatusCode)
	quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="Ens.StringRequest">
    <Method>PostAlert</Method>
  </MapItem>
</MapItems>
}

}
