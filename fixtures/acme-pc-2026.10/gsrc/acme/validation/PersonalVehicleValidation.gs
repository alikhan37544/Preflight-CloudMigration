package acme.validation

uses gw.api.database.Query

class PersonalVehicleValidation {
  // Query.make(PersonalVehicle) in prose must not be treated as SQL.
  function validate(vehicle : PersonalVehicle) : String {
    var note = "java.sql.Connection in a string is prose"
    if (vehicle.ModelYear < 1900) {
      return "Invalid model year"
    }
    return null
  }
}
