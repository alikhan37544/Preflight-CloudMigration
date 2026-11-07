package acme

class PersonalVehicleValidationTest extends GUnitTestClassBase {
  function testValidModelYear() {
    var vehicle = new PersonalVehicle()
    vehicle.ModelYear = 2020
    assertTrue(vehicle.ModelYear == 2020)
  }
}
