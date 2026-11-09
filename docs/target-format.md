# PreFlight Target Format Contract v1

**Scope:** Cloud Retrofit **without APD App** for a non-APD-native Personal Auto product.
**Status:** Local, non-deployable draft. Not an APD import, not a generated endpoint, not a tenant-validated artefact.

## 1. Files used by the process

| File | Role | Source/target |
|---|---|---|
| `<lob_prefix>_codegen_config_ext-1.0.yaml` | Defines REST API generation overrides. | Target draft |
| `template_gen_config.xml` | Defines the APD model structure for the non-APD path. | Read-only source input; not drafted |
| `policyperiod_<productCode>_ext-1.0.schema.json` | LOB extension schema. | Target draft |
| `policyperiod_<productCode>_ext-1.0.mapping.json` | LOB extension mapping. | Target draft |
| `policyperiod_<productCode>_ext-1.0.updater.json` | LOB extension updater. | Target draft |
| `<productCode>_ext-1.0.yaml` | Product access file exposing the installed product to Cloud API. | Target draft |

`_gen` files (schema/mapping/updater/swagger/Gosu resources) are codegen output. They are never edited or drafted. The prototype stops before endpoint generation.

## 2. Exact paths

```text
config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json
config/integration/mappings/ext/policyperiod/v1/policyperiod_pa_ext-1.0.mapping.json
config/integration/updaters/ext/policyperiod/v1/policyperiod_pa_ext-1.0.updater.json
config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml
config/integration/apis/installedlobs/pa_ext-1.0.yaml
```

Out of scope: `config/integration/apis/ext/policyperiod/v1/*.swagger.json`, `gsrc/gw/rest/ext/pc/policyperiod/pa/v1/*.gs`, `_gen` files, deployment.

## 3. Local schema (`preflight-target-v1`)

### 3.1 Schema draft

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "preflight-target-v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["modelYear", "make", "vin", "usage", "vehicleType"],
  "properties": {
    "modelYear": {"type": "integer", "minimum": 1900, "maximum": 2100},
    "make": {"type": "string", "maxLength": 80},
    "vin": {"type": "string", "minLength": 11, "maxLength": 17},
    "usage": {"type": "string", "enum": ["pleasure", "commute", "business"]},
    "vehicleType": {"type": "string", "enum": ["passenger", "motorcycle", "trailer"]},
    "garageLocation": {"type": "string", "maxLength": 80}
  }
}
```

### 3.2 Mapping draft

```json
{
  "schema_version": "1.0",
  "mappings": [
    {"source": "PersonalVehicle.ModelYear", "source_layer": "installed_entity", "target": "modelYear", "disposition": "mapped_transformed", "rule_id": "R-API-03", "provenance": "preflight-convention"},
    {"source": "PersonalVehicle.Make", "source_layer": "installed_entity", "target": "make", "disposition": "mapped_exact", "rule_id": "R-API-04", "provenance": "preflight-convention"},
    {"source": "PersonalVehicle.VIN", "source_layer": "installed_entity", "target": "vin", "disposition": "mapped_exact", "rule_id": "R-API-05", "provenance": "preflight-convention"},
    {"source": "PersonalVehicle.Usage", "source_layer": "installed_entity", "target": "usage", "disposition": "mapped_exact", "rule_id": "R-API-06", "provenance": "preflight-convention"},
    {"source": "PersonalVehicle.VehicleType", "source_layer": "installed_entity", "target": "vehicleType", "disposition": "mapped_exact", "rule_id": "R-API-01", "provenance": "preflight-convention"},
    {"source": "PersonalVehicle.GarageLocation_Ext", "source_layer": "installed_entity", "target": "garageLocation", "disposition": "mapped_transformed", "rule_id": "R-API-02", "provenance": "preflight-convention"},
    {"source": "VehicleType.Motorcycle_Ext", "source_layer": "typelist", "target": "vehicleType.motorcycle", "disposition": "mapped_transformed", "rule_id": "R-TYP-01", "provenance": "preflight-convention"},
    {"source": "PAVehicle", "source_layer": "apd_template", "target": "codegen.PAVehicle.nameOverride=PersonalVehicle", "disposition": "mapped_transformed", "rule_id": "R-CG-01", "provenance": "guidewire-doc"},
    {"source": "PAVehicle.Year", "source_layer": "apd_template", "target": "codegen.PAVehicle.fields.Year.nameOverride=ModelYear", "disposition": "mapped_transformed", "rule_id": "R-CG-02", "provenance": "guidewire-doc"},
    {"source": "PADriver", "source_layer": "apd_template", "target": "codegen.PADriver.nameOverride=VehicleDriver", "disposition": "mapped_transformed", "rule_id": "R-CG-03", "provenance": "guidewire-doc"},
    {"source": "PALine", "source_layer": "apd_template", "target": "codegen.PALine.nameOverride=PersonalAutoLine", "disposition": "mapped_transformed", "rule_id": "R-CG-04", "provenance": "guidewire-doc"},
    {"source": "PersonalAutoRatingFactorConfiguration", "source_layer": "apd_template", "target": "codegen.PersonalAutoRatingFactor.nameOverride=PersonalAutoRatingFactorConfiguration", "disposition": "mapped_transformed", "rule_id": "R-GW-24-01", "provenance": "guidewire-doc"}
  ]
}
```

### 3.3 Updater draft

```json
{
  "schema_version": "1.0",
  "create": {"modelYear": "ModelYear", "make": "Make", "vin": "VIN", "usage": "Usage", "vehicleType": "VehicleType", "garageLocation": "GarageLocation_Ext"},
  "update": {"modelYear": "ModelYear", "make": "Make", "vin": "VIN", "usage": "Usage", "vehicleType": "VehicleType", "garageLocation": "GarageLocation_Ext"}
}
```

### 3.4 Codegen draft (verified overrides)

```yaml
schema_version: "1.0"
types:
  PAVehicle:
    nameOverride: PersonalVehicle
    autonumber: VehicleNumber
    toCreateAndAdd: createAndAddVehicle
    toRemove: removeVehicle
    fields:
      Year:
        nameOverride: ModelYear
      GarageLocation:
        nameOverride: GarageLocation_Ext
        requiredForCreate: false
  PADriver:
    nameOverride: VehicleDriver
  PALine:
    nameOverride: PersonalAutoLine
  PersonalAutoRatingFactor:
    nameOverride: PersonalAutoRatingFactorConfiguration
wizardStepIds: false
```

### 3.5 Product access draft

```yaml
schema_version: "1.0"
productCode: pa
productName: PersonalAuto
enabled: true
```

## 4. Validation rules

- JSON files must parse and validate against `preflight-target-v1`.
- YAML files must parse with `safe_load` and validate against the local YAML shape.
- `_gen` files must not exist in the draft directory.
- Every mapping must have a rule ID and provenance.
- Every source property in the selected feature must have a disposition.
- Draft is labelled `local-draft`; no compile, generation, or tenant validation is claimed.

## 5. Provenance

- `guidewire-doc`: exact public doc URL + quote in `docs/claims-ledger.md`.
- `preflight-convention`: explicit reviewer decision required; UI shows the label.
- `reviewer-decision`: created by a reviewer during the run.

## 6. Sources

- Guidewire, “Files required for Cloud Retrofit process,” 22 Oct 2026. https://docs.guidewire.com/cloud/pc/202603/cloudapica/cloudAPI/topics/508-LOBEndpoints/01-generating-LOB-endpoints/c_files_required_for_cloud_retrofit.html
- Guidewire, “Files that define LOB-specific endpoints,” 22 Oct 2026. https://docs.guidewire.com/cloud/pc/202603/cloudapica/cloudAPI/topics/508-LOBEndpoints/01-generating-LOB-endpoints/c_files_that_define_lob_specific_endpoints.html
- Guidewire, “Codegen config file syntax,” 22 Oct 2026. https://docs.guidewire.com/cloud/pc/202603/cloudapica/cloudAPI/topics/508-LOBEndpoints/03-codegen-config-files/c_codegen_config_file_syntax.html
- Guidewire, “Correcting Cloud API LOB endpoint compile errors,” 2026.07. https://docs.guidewire.com/cloud/is/202607/cloudapica/cloudAPI/LOBEndpoints/generating-LOB-endpoints/c_correcting_compile_errors.html
