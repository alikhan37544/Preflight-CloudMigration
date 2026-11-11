package harbor.rating

uses java.sql.Connection
uses java.sql.DriverManager

class WindRatingLookup {
  function load(zone : String) : Connection {
    var conn = DriverManager.getConnection("jdbc:harbor:wind")
    var stmt = conn.createStatement()
    stmt.executeQuery("SELECT factor FROM wind_rating WHERE zone = '" + zone + "'")
    return conn
  }
}
