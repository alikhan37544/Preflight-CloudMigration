package acme.negatives

class CatchWithLogging {
  function safe() {
    try {
      maybeFail()
    } catch (e : Exception) {
      log.error(e.Message)
    }
  }
}
