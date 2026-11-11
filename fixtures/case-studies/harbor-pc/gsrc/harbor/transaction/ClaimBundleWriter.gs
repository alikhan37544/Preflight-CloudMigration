package harbor.transaction

class ClaimBundleWriter {
  function save(claim : Claim) {
    gw.transaction.Transaction.runWithNewBundle(\bundle -> {
      bundle.add(claim)
      bundle.commit()
    })
  }
}
