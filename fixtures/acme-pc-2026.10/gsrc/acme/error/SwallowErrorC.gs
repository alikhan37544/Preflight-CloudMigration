package acme.error

class SwallowErrorC {
  function risky() {
    try { maybeFail() } catch (e : Exception) { ; }
  }
}
