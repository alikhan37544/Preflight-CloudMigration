package cascade.rating

uses java.sql.Connection
uses java.sql.DriverManager

class VehicleRatingQuery {
  function loadFactor(vin : String) : Connection {
    var conn = DriverManager.getConnection("jdbc:cascade:rating")
    var stmt = conn.createStatement()
    stmt.executeQuery("SELECT factor FROM cascade_rating WHERE vin = '" + vin + "'")
    return conn
  }
}
