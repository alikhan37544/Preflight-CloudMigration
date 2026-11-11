package harbor.integration

uses javax.servlet.http.HttpServlet
uses javax.servlet.http.HttpServletRequest
uses javax.servlet.http.HttpServletResponse

class ClaimsGatewayServlet extends HttpServlet {
  override function doPost(req : HttpServletRequest, resp : HttpServletResponse) {
    resp.getWriter().write("claim accepted")
  }
}
