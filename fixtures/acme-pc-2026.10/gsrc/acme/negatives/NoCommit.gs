package acme.negatives

class NoCommit {
  function save(vehicle : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> {
      bundle.add(vehicle)
    })
  }
}
