"""Outbound alerts through the IRIS production: MEDDI.Alert.Service -> MEDDI.Alert.Operation -> POST to the MEDDI mock."""
import json
import logging

from app.config import settings

log = logging.getLogger(__name__)


def send_alert_via_iris(payload: dict) -> bool:
    """Queue one alert (level >= 2) in MEDDI.Production. False when IRIS or the production is down; never raises."""
    try:
        import iris

        connection = iris.connect(settings.iris_host, settings.iris_port, settings.iris_namespace,
                                  settings.iris_user, settings.iris_password, timeout=1)
        try:
            body = json.dumps(payload, ensure_ascii=False, default=str)
            return bool(iris.createIRIS(connection).classMethodValue("MEDDI.Alert.Service", "Send", body))
        finally:
            connection.close()
    except Exception as error:
        log.warning("IRIS alert not sent: %s", error)
        return False
