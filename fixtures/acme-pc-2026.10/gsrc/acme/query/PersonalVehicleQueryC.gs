package acme.query

uses java.sql.DriverManager

class PersonalVehicleQueryC {
  function load() {
    DriverManager.getConnection("jdbc:acme:vehicles")
  }
}
