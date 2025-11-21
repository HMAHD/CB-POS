using CB.POS.Core.Entities;

namespace CB.POS.Core.Interfaces.Services;

public interface ISessionContext
{
    Employee? CurrentEmployee { get; }
    void SetAuthentication(Employee employee);
    void Logout();
}
