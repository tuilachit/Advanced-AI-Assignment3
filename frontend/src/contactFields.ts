// Keep exact aliases aligned with backend/app/domain/profile_fields.py.
// Do not use prefixes: employer emails or private fields are not candidate contact details.
export const CONTACT_FIELD_ALIASES: Record<string, string[]> = {
  name: ['name'],
  email: ['email', 'contact_email', 'email_address'],
  phone: ['phone', 'contact_phone', 'phone_number'],
  github: ['github', 'github_url'],
  linkedin: ['linkedin', 'linkedin_url'],
  portfolio: ['portfolio', 'portfolio_url'],
  website: ['website', 'website_url'],
}

export function isContactField(field: string) {
  return Object.values(CONTACT_FIELD_ALIASES).some((aliases) => aliases.includes(field))
}
