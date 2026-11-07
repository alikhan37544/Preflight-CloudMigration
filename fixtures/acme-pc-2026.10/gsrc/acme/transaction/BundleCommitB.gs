package acme.transaction

class BundleCommitB {
  function save(v : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> {
      bundle.add(v)
      bundle.commit()
    })
  }
}
