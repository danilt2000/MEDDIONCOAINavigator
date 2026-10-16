#!/usr/bin/env sh
# Loads the MEDDI.* classes into FHIRSERVER and (re)starts MEDDI.Production with auto-start.
# Needs the meddi-iris container (docker compose up -d at the repo root). Safe to run again.
set -e
CONTAINER="${CONTAINER:-meddi-iris}"

MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p /home/irisowner/meddi/inbox/done
MSYS_NO_PATHCONV=1 docker exec -i "$CONTAINER" iris session IRIS -U FHIRSERVER <<'EOF'
set sc = $system.OBJ.LoadDir("/home/irisowner/meddi/src", "ck", .errors, 1) write !, "load: ", $select(sc:"OK", 1:$system.Status.GetErrorText(sc)), !
set sc = ##class(Ens.Director).StopProduction(10, 1)
set sc = ##class(Ens.Director).SetAutoStart("MEDDI.Production") write "auto-start: ", $select(sc:"OK", 1:$system.Status.GetErrorText(sc)), !
set sc = ##class(Ens.Director).StartProduction("MEDDI.Production") write "start: ", $select(sc:"OK", 1:$system.Status.GetErrorText(sc)), !
halt
EOF
