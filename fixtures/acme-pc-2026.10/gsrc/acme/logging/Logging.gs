package acme.logging

class Logging {
  function dump(vehicle : PersonalVehicle, e : Exception) {
    print("vehicle " + vehicle.VIN)
    System.out.println("model " + vehicle.ModelYear)
    e.printStackTrace()
    print("ssn=" + vehicle.Driver.SSN)
  }
}
