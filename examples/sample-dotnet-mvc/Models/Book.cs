namespace BookShelf.Models;

public class Book
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Author { get; set; } = "";
    public string Isbn { get; set; } = "";
    public string Status { get; set; } = "To read";
    public int UserId { get; set; }
}
