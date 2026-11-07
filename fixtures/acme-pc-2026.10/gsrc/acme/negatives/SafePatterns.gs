package acme.negatives

uses gw.api.database.Query

class SafePatterns {
  // DriverManager.getConnection in a comment is prose.
  var note = "java.sql.Connection in a string is prose"
  function useQuery() {
    var q = Query.make(PersonalVehicle)
    q.select()
  }
}
