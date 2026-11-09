package acme.negatives

class CatchAndRethrow {
  function safe() {
    try {
      maybeFail()
    } catch (e : Exception) {
      throw new RuntimeException("vehicle lookup failed", e)
    }
  }
}
