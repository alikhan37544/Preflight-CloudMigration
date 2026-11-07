package acme.query

uses java.sql.Connection
uses java.sql.DriverManager

class PersonalVehicleQuery {
  function load() : Connection {
    var conn = DriverManager.getConnection("jdbc:acme:vehicles")
    var stmt = conn.createStatement()
    stmt.executeQuery("SELECT * FROM pv_vehicle")
    return conn
  }
}
