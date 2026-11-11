package cascade.integration

uses gw.plugin.messaging.IMessageTransport
uses javax.jms.Message

class PolicyMessagingPlugin implements IMessageTransport {
  override function send(message : Message) {
    // Legacy JMS bridge to the commission system.
  }
}
