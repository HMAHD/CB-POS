namespace CB.POS.Core.Interfaces.Services;

public interface IFocusService
{
    /// <summary>
    /// Registers the main barcode input element as the default return point.
    /// </summary>
    /// <param name="inputControl">The UI element (TextBox) to focus on.</param>
    void RegisterMainInput(object inputControl);

    /// <summary>
    /// Forces focus back to the main input. 
    /// Call this after any modal closes or button click finishes.
    /// </summary>
    void ResetFocusToInput();

    /// <summary>
    /// Temporarily suspends auto-focus (e.g., when typing in a search box).
    /// </summary>
    void SuspendAutoFocus();

    /// <summary>
    /// Resumes auto-focus behavior.
    /// </summary>
    void ResumeAutoFocus();
}