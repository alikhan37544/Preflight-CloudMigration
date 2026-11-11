package cascade.transaction

class BundleWriter {
  function save(vehicle : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> {
      bundle.add(vehicle)
      bundle.commit()
    })
  }
}
