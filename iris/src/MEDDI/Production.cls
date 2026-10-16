/// MEDDI ONCO: HL7v2 lab results in (file drop -> SDA3 -> FHIR repository), monitoring-centre alerts out (HTTP POST).
Class MEDDI.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="MEDDI.Production" TestingEnabled="true" LogGeneralTraceEvents="false">
  <Description>MEDDI ONCO navigator: HL7v2 ORU^R01 labs into the FHIR repository, level 2-4 alerts to the MEDDI monitoring centre</Description>
  <ActorPoolSize>1</ActorPoolSize>
  <Item Name="MEDDI.LabHL7.Service" ClassName="EnsLib.HL7.Service.FileService" PoolSize="1" Enabled="true" Foreground="false">
    <Setting Target="Adapter" Name="FilePath">/home/irisowner/meddi/inbox/</Setting>
    <Setting Target="Adapter" Name="FileSpec">*.hl7</Setting>
    <Setting Target="Adapter" Name="ArchivePath">/home/irisowner/meddi/inbox/done/</Setting>
    <Setting Target="Host" Name="MessageSchemaCategory">2.5.1</Setting>
    <Setting Target="Host" Name="DefCharEncoding">UTF-8</Setting>
    <Setting Target="Host" Name="TargetConfigNames">MEDDI.LabHL7.Process</Setting>
  </Item>
  <Item Name="MEDDI.LabHL7.Process" ClassName="MEDDI.LabHL7.Process" PoolSize="1" Enabled="true" Foreground="false">
    <Setting Target="Host" Name="TargetConfigName">MEDDI.SDA3ToFHIR</Setting>
  </Item>
  <Item Name="MEDDI.SDA3ToFHIR" ClassName="HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process" PoolSize="1" Enabled="true" Foreground="false">
    <Setting Target="Host" Name="TargetConfigName">HS.FHIRServer.Interop.Operation</Setting>
    <Setting Target="Host" Name="FHIRMetadataSet">HL7v40 / Base HL7 Metadata</Setting>
    <Setting Target="Host" Name="FHIREndpoint">/fhir/r4</Setting>
    <Setting Target="Host" Name="TransformClass">MEDDI.LabHL7.Transform</Setting>
  </Item>
  <Item Name="HS.FHIRServer.Interop.Operation" ClassName="HS.FHIRServer.Interop.Operation" PoolSize="1" Enabled="true" Foreground="false">
  </Item>
  <Item Name="MEDDI.Alert.Service" ClassName="MEDDI.Alert.Service" PoolSize="0" Enabled="true" Foreground="false">
    <Setting Target="Host" Name="TargetConfigName">MEDDI.Alert.Operation</Setting>
  </Item>
  <Item Name="MEDDI.Alert.Operation" ClassName="MEDDI.Alert.Operation" PoolSize="1" Enabled="true" Foreground="false">
    <Setting Target="Adapter" Name="HTTPServer">host.docker.internal</Setting>
    <Setting Target="Adapter" Name="HTTPPort">8100</Setting>
    <Setting Target="Adapter" Name="URL">/mock/meddi/requests</Setting>
  </Item>
</Production>
}

}
