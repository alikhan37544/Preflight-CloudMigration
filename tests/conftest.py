"""Shared pytest fixtures for PreFlight.

All fixtures are deliberately tiny synthetic Guidewire-style estates.
They never touch the real fixture directories.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def tiny_snapshot(tmp_path: Path) -> Path:
    """A minimal, legal snapshot with supported and unsupported files."""
    root = tmp_path / "snapshot"
    write(
        root / "config/metadata/entity/PersonalVehicle.eti",
        """<?xml version="1.0" encoding="UTF-8"?>
<entity name="PersonalVehicle">
  <column name="ModelYear" type="Integer"/>
  <column name="Make" type="Text"/>
  <column name="VIN" type="Text"/>
  <column name="Usage" type="TypeKey" typelist="VehicleUsage"/>
</entity>
""",
    )
    write(
        root / "config/extensions/entity/PersonalVehicle.etx",
        """<?xml version="1.0" encoding="UTF-8"?>
<entityExtension name="PersonalVehicle">
  <column name="GarageLocation_Ext" type="Text"/>
  <column name="Territory_Ext" type="Integer"/>
</entityExtension>
""",
    )
    write(
        root / "config/metadata/typelist/VehicleType.tti",
        """<?xml version="1.0" encoding="UTF-8"?>
<typelist name="VehicleType">
  <code name="Passenger"/>
  <code name="Trailer"/>
</typelist>
""",
    )
    write(
        root / "config/extensions/typelist/VehicleType.ttx",
        """<?xml version="1.0" encoding="UTF-8"?>
<typelistExtension name="VehicleType">
  <code name="Motorcycle_Ext"/>
</typelistExtension>
""",
    )
    write(
        root / "config/web/pcf/policy/PAVehicleDV.pcf",
        """<?xml version="1.0" encoding="UTF-8"?>
<PCF name="PAVehicleDV">
  <Screen>
    <TypeKeyInput id="VehicleType" value="VehicleType"/>
    <TextInput id="ModelYear" value="ModelYear"/>
    <TextInput id="GarageLocation_Ext" value="GarageLocation_Ext"/>
  </Screen>
</PCF>
""",
    )
    write(
        root / "config/resources/productmodel/PersonalAuto.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<productModel name="PersonalAuto">
  <type name="PAVehicle"/>
</productModel>
""",
    )
    write(
        root / "gsrc/acme/validation/PersonalVehicleValidation.gs",
        """package acme.validation

class PersonalVehicleValidation {
  function validate(vehicle : PersonalVehicle) : String {
    if (vehicle.ModelYear < 1900) {
      return "Invalid model year"
    }
    return null
  }
}
""",
    )
    write(
        root / "gtest/acme/PersonalVehicleValidationTest.gs",
        """package acme

class PersonalVehicleValidationTest extends GUnitTestClassBase {
  function testValidYear() {
    assertTrue(true)
  }
}
""",
    )
    write(root / "config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml",
          "types:\n  PAVehicle:\n    nameOverride: PersonalVehicle\n")
    write(root / "README.txt", "Synthetic fixture. No customer data.\n")
    write(root / "assets/logo.png", "\x89PNG\r\n\x1a\n\x00\x00binary")
    write(root / "config/broken.xml", "<not-closed>")
    return root


@pytest.fixture()
def manifest_fixture(tiny_snapshot: Path) -> Path:
    """Alias kept readable in tests."""
    return tiny_snapshot


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    """Hash of sorted (relative path, file hash) pairs."""
    pairs = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            pairs.append((path.relative_to(root).as_posix(), sha256_file(path)))
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
