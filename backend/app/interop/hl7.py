"""MEDDI laboratore -> HL7v2 2.5.1 ORU^R01, one message per blood draw (odber_id).

python -m app.interop.hl7 --patient ONC-001          print the messages
python -m app.interop.hl7 --patient ONC-001 --drop   write them to iris/inbox for MEDDI.LabHL7.Service
python -m app.interop.hl7 --patient ONC-001 --new    drop the last draw again as a new draw taken now (demo)
"""
import argparse
import os
from datetime import datetime
from itertools import groupby
from zoneinfo import ZoneInfo

from app.adapters.meddi_json import load_patient
from app.config import REPO_ROOT, settings
from app.models import Lab, Patient

INBOX = REPO_ROOT / "iris" / "inbox"

LOINC = {
    "leu": ("6690-2", "Leukocytes [#/volume] in Blood by Automated count"),
    "neu": ("751-8", "Neutrophils [#/volume] in Blood by Automated count"),
    "hb": ("718-7", "Hemoglobin [Mass/volume] in Blood"),
    "plt": ("777-3", "Platelets [#/volume] in Blood by Automated count"),
    "kreat": ("14682-9", "Creatinine [Moles/volume] in Serum or Plasma"),
    "na": ("2951-2", "Sodium [Moles/volume] in Serum or Plasma"),
    "k": ("2823-3", "Potassium [Moles/volume] in Serum or Plasma"),
    "alt": ("1742-6", "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
    "bili": ("14631-6", "Bilirubin.total [Moles/volume] in Serum or Plasma"),
    "crp": ("1988-5", "C reactive protein [Mass/volume] in Serum or Plasma"),
    "tsh": ("3016-3", "Thyrotropin [Units/volume] in Serum or Plasma"),
    "ft4": ("14920-3", "Thyroxine (T4) free [Moles/volume] in Serum or Plasma"),
    "mg": ("2601-3", "Magnesium [Moles/volume] in Serum or Plasma"),
    "inr": ("6301-6", "INR in Platelet poor plasma by Coagulation assay"),
    "alb": ("1751-7", "Albumin [Mass/volume] in Serum or Plasma"),
    "psa": ("2857-1", "Prostate specific Ag [Mass/volume] in Serum or Plasma"),
    "testo": ("14913-8", "Testosterone [Moles/volume] in Serum or Plasma"),
    "glu": ("14749-6", "Glucose [Moles/volume] in Serum or Plasma"),
    "moc_bilk": ("20454-5", "Protein [Presence] in Urine by Test strip"),
    "ntprobnp": ("33762-6", "Natriuretic peptide.B prohormone N-Terminal [Mass/volume] in Serum or Plasma"),
    "ca": ("2000-8", "Calcium [Moles/volume] in Serum or Plasma"),
    "ca125": ("10334-1", "Cancer Ag 125 [Units/volume] in Serum or Plasma"),
    "ddimer": ("48065-7", "Fibrin D-dimer FEU [Mass/volume] in Platelet poor plasma"),
    "ketony": ("53060-9", "3-Hydroxybutyrate [Moles/volume] in Blood"),
    "ph": ("2744-1", "pH of Arterial blood"),
}


def escape(text: str) -> str:
    for char, code in (("\\", "\\E\\"), ("|", "\\F\\"), ("^", "\\S\\"), ("&", "\\T\\"), ("~", "\\R\\")):
        text = text.replace(char, code)
    return text


def hl7_time(at: datetime) -> str:
    return at.replace(tzinfo=ZoneInfo(settings.timezone)).strftime("%Y%m%d%H%M%S%z")


def ucum(unit: str) -> str:
    return unit.replace("^", "*").replace("µ", "u").replace("/l", "/L")


def number(value: float) -> str:
    return f"{value:g}"


def oru_message(patient: Patient, labs: list[Lab]) -> str:
    first = labs[0]
    at = hl7_time(first.timestamp)
    given, _, family = patient.demografie.jmeno_fiktivni.partition(" ")
    birth_year = patient.obdobi_sledovani["od"].year - patient.demografie.vek
    segments = [
        f"MSH|^~\\&|LIS|LAB|MEDDI_NAV|MEDDI|{at}||ORU^R01^ORU_R01|{first.odber_id}|P|2.5.1||||||UNICODE UTF-8",
        f"PID|1||{patient.patient_id}^^^MEDDI^MR||{escape(family.rstrip('.'))}^{escape(given)}||{birth_year}0101|{patient.demografie.pohlavi}",
        f"ORC|RE|{first.odber_id}|{first.odber_id}" + "|" * 26 + "LAB",
        f"OBR|1|{first.odber_id}|{first.odber_id}|26436-6^Laboratory studies (set)^LN|||{at}||||||||||||||||||F",
    ]
    for index, lab in enumerate(labs, 1):
        code, name = LOINC[lab.kod]
        segments.append(
            f"OBX|{index}|NM|{code}^{escape(name)}^LN||{number(lab.hodnota)}|{escape(ucum(lab.jednotka))}"
            f"|{number(lab.ref_min)}-{number(lab.ref_max)}|{lab.priznak or 'N'}|||F|||{at}"
        )
    return "\r".join(segments) + "\r"


def patient_messages(patient: Patient) -> dict[str, str]:
    labs = sorted(patient.laboratore, key=lambda lab: (lab.timestamp, lab.odber_id))
    return {odber_id: oru_message(patient, list(group)) for odber_id, group in groupby(labs, key=lambda lab: lab.odber_id)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--patient", required=True)
    parser.add_argument("--drop", action="store_true", help="write the messages to iris/inbox")
    parser.add_argument("--new", action="store_true", help="drop the last draw as a new draw taken now")
    args = parser.parse_args()
    patient = load_patient(args.patient)
    if args.new:
        last = max(patient.laboratore, key=lambda lab: (lab.timestamp, lab.odber_id)).odber_id
        from app.store import DEFAULT_NOW

        now = datetime.fromisoformat(os.environ.get("DEMO_NOW", DEFAULT_NOW)).astimezone(ZoneInfo(settings.timezone))
        draw = f"{last}-N{now:%H%M%S}"
        labs = [lab.model_copy(update={"odber_id": draw, "datum": now.date(), "cas": f"{now:%H:%M}"})
                for lab in patient.laboratore if lab.odber_id == last]
        path = INBOX / f"{draw}.hl7"
        path.write_bytes(oru_message(patient, labs).encode("utf-8"))
        print(f"dropped {path} ({len(labs)} results)")
        return
    for odber_id, message in patient_messages(patient).items():
        if args.drop:
            path = INBOX / f"{odber_id}.hl7"
            path.write_bytes(message.encode("utf-8"))
            print(f"dropped {path}")
        else:
            print(message.replace("\r", "\n"))


if __name__ == "__main__":
    main()
