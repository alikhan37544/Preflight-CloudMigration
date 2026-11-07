package acme.query

uses java.sql.Statement

class PersonalVehicleQueryB {
  function load(stmt : Statement) {
    stmt.executeQuery("SELECT VIN FROM pv_vehicle")
  }
}
