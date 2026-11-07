package acme.integration

uses javax.servlet.http.HttpServlet
uses javax.servlet.http.HttpServletRequest
uses javax.servlet.http.HttpServletResponse

class LegacyVehicleServlet extends HttpServlet {
  override function doGet(req : HttpServletRequest, resp : HttpServletResponse) {
    resp.getWriter().write("vehicles")
  }
}
