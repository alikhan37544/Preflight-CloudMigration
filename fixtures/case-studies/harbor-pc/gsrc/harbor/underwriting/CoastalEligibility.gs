package harbor.underwriting

uses gw.internal.util.ReflectionUtil
uses javax.ejb.SessionBean

class CoastalEligibility {
  private static var eligibilityCache : java.util.Map = new java.util.HashMap()

  function decide(dwelling : HomeownersDwelling) : boolean {
    ReflectionUtil.reload()
    var key = dwelling.CoastalZone.DisplayName
    if (eligibilityCache.containsKey(key)) {
      return eligibilityCache.get(key) as boolean
    }
    var eligible = dwelling.WindMitigationCredit > 0.15
    eligibilityCache.put(key, eligible)
    return eligible
  }
}
