package acme.error

class SwallowError {
  function risky() {
    try {
      maybeFail()
    } catch (e : Exception) {
      // ignored on purpose
    }
  }
}
