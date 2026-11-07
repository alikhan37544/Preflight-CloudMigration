package acme.negatives
uses com.guidewire.public.api.Thing
uses gw.api.database.Query
class PublicApi { function run() { Query.make(PersonalVehicle) } }
