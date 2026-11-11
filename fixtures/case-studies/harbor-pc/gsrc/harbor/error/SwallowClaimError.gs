package harbor.error

class SwallowClaimError {
  function notify() {
    try {
      maybeFail()
    } catch (e : Exception) {
    }
  }
}
