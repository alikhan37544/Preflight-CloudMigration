package acme.transaction

class BundleCommit {
  function save(vehicle : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> {
      bundle.add(vehicle)
      bundle.commit()
    })
  }
}
