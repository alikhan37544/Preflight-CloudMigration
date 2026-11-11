package harbor.integration

uses gw.plugin.messaging.IMessageTransport
uses javax.jms.Message

class VendorMqPublisher implements IMessageTransport {
  override function send(message : Message) {
    // Publish to the on-premises vendor MQ estate.
  }
}
