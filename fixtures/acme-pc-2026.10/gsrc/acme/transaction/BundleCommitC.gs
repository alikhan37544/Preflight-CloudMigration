package acme.transaction

class BundleCommitC {
  function save(v : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> { bundle.add(v); bundle.commit() })
  }
}
