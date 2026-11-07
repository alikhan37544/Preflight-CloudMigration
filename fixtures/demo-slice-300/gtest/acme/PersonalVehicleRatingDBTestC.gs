package acme
class PersonalVehicleRatingDBTestC extends GUnitTestClassBase {
  function testRows() { DriverManager.getConnection("jdbc:acme") }
}
