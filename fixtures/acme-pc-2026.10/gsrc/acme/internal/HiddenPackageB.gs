package acme.internal

uses gw.internal.util.ReflectionUtil

class HiddenPackageB {
  function boot() { ReflectionUtil.reload() }
}
