package harbor.logging

class ClaimLogger {
  function dump(claim : Claim) {
    System.out.println("claim ssn=" + claim.SSN)
  }
}
