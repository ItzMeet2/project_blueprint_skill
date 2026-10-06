using Microsoft.AspNetCore.Mvc;

namespace BookShelf.Controllers;

[Route("account")]
public class AccountController : Controller
{
    [HttpGet("login")]
    public IActionResult Login() => View();

    [HttpPost("login")]
    public IActionResult Login(string email, string password)
    {
        // TODO: verify credentials
        return RedirectToAction("Index", "Books");
    }

    [HttpGet("register")]
    public IActionResult Register() => View();

    [HttpPost("register")]
    public IActionResult Register(string email, string password)
    {
        return RedirectToAction("Login");
    }

    [HttpPost("logout")]
    public IActionResult Logout()
    {
        return RedirectToAction("Index", "Home");
    }
}
