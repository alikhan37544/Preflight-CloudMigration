package acme

class PersonalVehicleRatingDBTest extends GUnitTestClassBase {
  function testRatingRows() {
    var q = Query.make(PersonalVehicle)
    var rows = q.select().toList()
    loadSampleData()
    assertTrue(rows.size() >= 0)
  }
}
