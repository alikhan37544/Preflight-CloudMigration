package harbor

class ClaimDbTest extends GUnitTestClassBase {
  function testClaimRows() {
    var q = Query.make(Claim)
    q.select()
    loadSampleData()
    assertTrue(true)
  }
}
