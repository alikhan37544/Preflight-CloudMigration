package acme.rating

class PersonalVehicleRating {
  function factor(vehicle : PersonalVehicle) : int {
    return vehicle.ModelYear >= 2010 ? 100 : 120
  }
}
