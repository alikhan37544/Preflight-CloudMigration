package acme
class PersonalVehicleRatingDBTestB extends GUnitTestClassBase {
  function testRows() { var q = Query.make(PersonalVehicle); q.select(); loadSampleData() }
}
