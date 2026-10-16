#!/usr/bin/env sh
# Points MEDDI.Alert.Operation at another port of the host API and applies it to the running production.
# Usage: sh iris/scripts/set-alert-target.sh 8103   (restore: ... 8100)
set -e
PORT="${1:?port}"
MSYS_NO_PATHCONV=1 docker exec -i "${CONTAINER:-meddi-iris}" iris session IRIS -U FHIRSERVER <<EOF
set production = ##class(Ens.Config.Production).%OpenId("MEDDI.Production"), item = production.FindItemByConfigName("MEDDI.Alert.Operation")
for i = 1:1:item.Settings.Count() { set setting = item.Settings.GetAt(i) if setting.Name = "HTTPPort" { set setting.Value = "$PORT" } }
set sc = production.%Save() set:sc sc = production.SaveToClass() set:sc sc = ##class(Ens.Director).UpdateProduction(10, 1) write !, "alert target port $PORT: ", \$select(sc:"OK", 1:\$system.Status.GetErrorText(sc)), !
halt
EOF
